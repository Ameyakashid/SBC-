import base64
import hashlib
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from chatgpt import ChatGPTClient, ChatGPTError, TOKEN, RESOURCE

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = ChatGPTClient(self.tmp.name)

    def begin(self):
        with patch.object(self.client, '_dependency'):
            result = self.client.begin('http://127.0.0.1:8765/auth/callback')
        return {k:v[0] for k,v in parse_qs(urlparse(result['authorization_url']).query).items()}

    def test_pkce_host_and_no_credentials_in_status(self):
        a = self.begin()
        expected = base64.urlsafe_b64encode(hashlib.sha256(self.client.pending['verifier'].encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(a['code_challenge'], expected)
        self.assertEqual(a['client_id'], 'dynamic_agent_client')
        self.assertTrue(a['ext_agent_host_id'].startswith('urn:uuid:'))
        self.assertNotIn('access_token', self.client.status())
        b = self.begin()
        self.assertEqual(a['ext_agent_host_id'], b['ext_agent_host_id'])
        self.assertNotEqual(a['state'], b['state'])

    def test_loopback_only(self):
        with patch.object(self.client, '_dependency'):
            for uri in ['http://localhost:8765/auth/callback', 'https://example.com/auth/callback', 'http://127.0.0.1:8765/callback']:
                with self.assertRaises(ChatGPTError): self.client.begin(uri)

    def test_wrong_state_never_exchanges(self):
        self.begin()
        with patch('chatgpt._json_request') as network:
            with self.assertRaises(ChatGPTError):
                self.client.finish({'state':'wrong','client_id':'oaiapp_example','code':'secret'})
            network.assert_not_called()

    def test_success_and_replay(self):
        a = self.begin()
        tokens = {'access_token':'fake-access','refresh_token':'fake-refresh','id_token':'fake-id',
                  'token_type':'Bearer','expires_in':3600,'scope':'openid chatgpt.tokens.use.direct'}
        with patch('chatgpt._json_request', return_value=tokens) as network, patch.object(self.client, '_identity', return_value={'email':'test@example.invalid','sub':'user1','iss':'https://auth.openai.com'}):
            result = self.client.finish({'state':a['state'],'client_id':'oaiapp_example','code':'fake-code'})
            self.assertTrue(result['sharing'])
            self.assertEqual(network.call_args.args[0], TOKEN)
            self.assertEqual(network.call_args.args[1]['client_id'], 'oaiapp_example')
            self.assertEqual(network.call_args.args[1]['resource'], RESOURCE)
            with self.assertRaises(ChatGPTError):
                self.client.finish({'state':a['state'],'client_id':'oaiapp_example','code':'fake-code'})
        self.assertEqual((self.client.directory / 'chatgpt.json').stat().st_mode & 0o777, 0o600)

    def test_identity_failure_does_not_save_tokens(self):
        a = self.begin()
        with patch('chatgpt._json_request', return_value={'access_token':'do-not-save'}), patch.object(self.client, '_identity', side_effect=ChatGPTError('bad signature')):
            with self.assertRaises(ChatGPTError):
                self.client.finish({'state':a['state'],'client_id':'oaiapp_example','code':'fake'})
        disk = json.loads((self.client.directory / 'chatgpt.json').read_text())
        self.assertEqual(disk['client_id'], 'oaiapp_example')
        self.assertNotIn('access_token', disk)

    def test_denial_is_one_shot(self):
        a = self.begin()
        with patch('chatgpt._json_request') as network:
            with self.assertRaises(ChatGPTError): self.client.finish({'state':a['state'],'error':'access_denied'})
            network.assert_not_called()
            self.assertIsNone(self.client.pending)

    def test_catalog_and_refresh(self):
        self.client.record.update(access_token='old', refresh_token='refresh', client_id='oaiapp_example', scopes=['chatgpt.tokens.use.direct'], expires_at=0)
        responses = [{'access_token':'new','refresh_token':'rotated','token_type':'Bearer','expires_in':3600},
                     {'models':[{'slug':'available','display_name':'Available','visibility':'list'},{'slug':'hidden','visibility':'hidden'}]}]
        with patch('chatgpt._json_request', side_effect=responses) as network:
            self.assertEqual(self.client.models(), [{'slug':'available','display_name':'Available'}])
            self.assertEqual(network.call_args.kwargs['token'], 'new')
        self.assertEqual(self.client.record['refresh_token'], 'rotated')


    def test_logout_allows_different_account_with_new_registration(self):
        original = self.begin()
        self.client.record.update(client_id='oaiapp_old', subject='old-user', issuer='https://auth.openai.com',
                                  email='old@example.invalid', access_token='old-secret', scopes=['chatgpt.tokens.use.direct'])
        self.client.logout()
        self.assertFalse(self.client.status()['connected'])
        self.assertNotIn('subject', self.client.record)
        self.assertNotIn('client_id', self.client.record)
        self.assertEqual(self.client.record['signed_out_profiles'][0]['client_id'], 'oaiapp_old')
        self.assertNotIn('access_token', self.client.record['signed_out_profiles'][0])
        new = self.begin()
        self.assertEqual(new['client_id'], 'dynamic_agent_client')
        self.assertEqual(original['ext_agent_host_id'], new['ext_agent_host_id'])
        tokens = {'access_token':'new-secret','token_type':'Bearer','expires_in':3600,'scope':'chatgpt.tokens.use.direct'}
        identity = {'sub':'different-user','iss':'https://auth.openai.com','email':'new@example.invalid'}
        with patch('chatgpt._json_request', return_value=tokens), patch.object(self.client, '_identity', return_value=identity):
            result = self.client.finish({'state':new['state'],'client_id':'oaiapp_new','code':'fake'})
        self.assertTrue(result['sharing'])
        self.assertEqual(self.client.record['subject'], 'different-user')
        self.assertEqual(self.client.record['client_id'], 'oaiapp_new')

    def test_incomplete_stream_rejected(self):
        import io
        self.client.record.update(access_token='fake', scopes=['chatgpt.tokens.use.direct'], expires_at=time.time()+3600)
        partial = io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n')
        with patch.object(self.client, 'models', return_value=[{'slug':'test'}]), patch('urllib.request.urlopen', return_value=partial):
            with self.assertRaises(ChatGPTError): self.client.explain('test', 'Explain')

    def test_completed_stream(self):
        import io
        self.client.record.update(access_token='fake', scopes=['chatgpt.tokens.use.direct'], expires_at=time.time()+3600)
        stream = io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"ok"}\n\ndata: {"type":"response.completed"}\n\n')
        with patch.object(self.client, 'models', return_value=[{'slug':'test'}]), patch('urllib.request.urlopen', return_value=stream) as network:
            self.assertEqual(self.client.explain('test', 'Explain'), 'ok')
            payload = json.loads(network.call_args.args[0].data)
            self.assertFalse(payload['store']); self.assertTrue(payload['stream'])
            self.assertIsInstance(payload['input'], list)

if __name__ == '__main__': unittest.main()

class IdentityVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import jwt
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError:
            raise unittest.SkipTest('Optional ChatGPT crypto dependencies not installed')
        cls.jwt = jwt
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def test_real_signature_and_claim_validation(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            client = ChatGPTClient(directory)
            claims = {'iss':'https://auth.openai.com','aud':'oaiapp_test','sub':'subject','iat':int(time.time()),'exp':int(time.time())+60,'nonce':'expected'}
            config = {'issuer':'https://auth.openai.com','jwks_uri':'https://auth.openai.com/.well-known/jwks.json','id_token_signing_alg_values_supported':['RS256']}
            with patch('chatgpt._json_request', return_value=config), patch('jwt.PyJWKClient') as jwks:
                jwks.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())
                valid = self.jwt.encode(claims, self.key, algorithm='RS256')
                self.assertEqual(client._identity(valid, 'oaiapp_test', 'expected')['sub'], 'subject')
                for changed in [dict(claims, aud='other'), dict(claims, nonce='other'), dict(claims, exp=1), dict(claims, iss='https://evil.invalid')]:
                    with self.assertRaises(ChatGPTError):
                        client._identity(self.jwt.encode(changed, self.key, algorithm='RS256'), 'oaiapp_test', 'expected')
                with self.assertRaises(ChatGPTError):
                    client._identity(self.jwt.encode(claims, 'malicious-secret-long-enough-for-test-only', algorithm='HS256'), 'oaiapp_test', 'expected')
