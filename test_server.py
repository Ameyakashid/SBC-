import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import server

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()
    def request(self,path,body=None,headers=None,raw=None):
        h={'X-SBC-Token':server.TOKEN,'Content-Type':'application/json'}
        h.update(headers or {})
        payload=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request=urllib.request.Request(self.url+path,data=payload,headers=h)
        try:
            with urllib.request.urlopen(request) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
    def test_import_solve_and_repeat(self):
        demo=(server.ROOT/'demo-club.json').read_text()
        code,raw=self.request('/api/import',{'text':demo,'format':'json'})
        self.assertEqual(code,200);players=json.loads(raw)['players']
        data={'players':players,'constraints':{'squadSize':11,'minAverageRating':80,'minRare':3,'minLeagues':2,'budget':20000,'minTotalItemScore':0}}
        a=self.request('/api/solve',data);b=self.request('/api/solve',data)
        self.assertEqual(a,b);result=json.loads(a[1]);self.assertEqual(len(result['squad']),11)
        self.assertTrue(all(not p['protected'] and not p['startingXI'] for p in result['squad']))
    def test_malformed_and_unsupported(self):
        self.assertEqual(self.request('/api/import',{'text':'not-json'})[0],400)
        self.assertEqual(self.request('/api/import',raw=b'{"text":"[]","text":"[]"}')[0],400)
        malicious=b'{"players":[{"id":"x","name":"X","rating":80,"protected":true,"protected":false}],"constraints":{"squadSize":1}}'
        self.assertEqual(self.request('/api/solve',raw=malicious)[0],400)
        demo=json.loads((server.ROOT/'demo-club.json').read_text())
        self.assertEqual(self.request('/api/solve',{'players':demo,'constraints':{'chemistry':33}})[0],400)
    def test_security_boundaries(self):
        for h in [{'Host':'evil.test'},{'Origin':'https://evil.test'},{'Origin':'null'},{'X-SBC-Token':'wrong'}]:
            self.assertEqual(self.request('/api/solve',{},h)[0],403)
        for path in ['/.local/chatgpt.json','/../server.py','/core.py']:
            self.assertEqual(self.request(path)[0],404)
    def test_consent_and_callback_errors(self):
        with patch.object(server.CHATGPT,'begin') as begin:
            self.assertEqual(self.request('/api/chatgpt/start',{})[0],400);begin.assert_not_called()
            begin.return_value={'authorization_url':'https://auth.openai.com/test'}
            self.assertEqual(self.request('/api/chatgpt/start',{'consentToLocalStorage':True})[0],200)
        with patch.object(server.CHATGPT,'finish') as finish:
            code,body=self.request('/auth/callback?state=a&state=b');self.assertEqual(code,200);self.assertIn(b'Duplicate',body);finish.assert_not_called()
            finish.side_effect=ValueError('Sign-in canceled')
            self.assertIn(b'Sign-in canceled',self.request('/auth/callback?state=valid')[1])
    def test_llm_proposal_review_then_solve(self):
        c={'squadSize':11,'minAverageRating':80,'minRare':5,'minLeagues':2,'budget':15000,'minTotalItemScore':0}
        with patch.object(server.CHATGPT,'explain',return_value=json.dumps({'constraints':c,'explanation':'Five rares, lower budget.'})):
            code,body=self.request('/api/chatgpt/propose',{'model':'test','instruction':'Use five rares','constraints':c})
            self.assertEqual(code,200);proposal=json.loads(body)
        demo=json.loads((server.ROOT/'demo-club.json').read_text())
        code,body=self.request('/api/solve',{'players':demo,'constraints':proposal['constraints']})
        self.assertEqual(code,200);result=json.loads(body);self.assertGreaterEqual(result['metrics']['rare'],5)
    def test_llm_unsupported_and_failure_do_not_apply(self):
        c={'squadSize':11,'minAverageRating':80,'minRare':3,'minLeagues':2,'budget':20000,'minTotalItemScore':0}
        for output in ['not json',json.dumps({'constraints':{'chemistry':33},'explanation':'bad'})]:
            with patch.object(server.CHATGPT,'explain',return_value=output):
                self.assertEqual(self.request('/api/chatgpt/propose',{'model':'test','instruction':'More rares','constraints':c})[0],400)
        with patch.object(server.CHATGPT,'explain',side_effect=ValueError('Stream did not complete')):
            code,body=self.request('/api/chatgpt/explain',{'model':'test','prompt':'hello'})
            self.assertEqual(code,400);self.assertIn(b'Stream did not complete',body)

class AdvisorHTTPTests(HTTPTests):
    def payload(self):
        return {'model':'test','players':json.loads((server.ROOT/'demo-club.json').read_text()),
                'brief':'Fictional one-player SBC. Preserve favourites. No chemistry requirement.',
                'platform':'pc','budget':1000,'consentToWholeClubSharing':True}
    def response(self):
        return {'status':'advice','summary':'Use a supplied duplicate, avoiding purchases.', 'missingFields':['Reward value not supplied'],
                'recommended':{'title':'Owned duplicate','type':'owned_only','ownedIds':['demo-1'],'buyIds':[],
                'reasoning':'Uses a supplied duplicate; verify all in-game requirements. No live prices available.',
                'confidence':'low','missingFields':['Reward value not supplied']},'alternatives':[]}
    def test_whole_club_advisor_http(self):
        with patch.object(server.CHATGPT,'explain',return_value=json.dumps(self.response())) as model:
            code,body=self.request('/api/advisor',self.payload());self.assertEqual(code,200)
            r=json.loads(body);self.assertFalse(r['fullSbcVerified']);self.assertEqual(r['recommended']['purchaseCost'],0)
            prompt=model.call_args.args[1];self.assertIn('demo-18',prompt);self.assertIn('startingXI',prompt)
    def test_advisor_consent_before_network(self):
        data=self.payload();data['consentToWholeClubSharing']=False
        with patch.object(server.CHATGPT,'explain') as model:
            self.assertEqual(self.request('/api/advisor',data)[0],400);model.assert_not_called()
    def test_advisor_protected_plan_rejected(self):
        result=self.response();result['recommended']['ownedIds']=['demo-17']
        with patch.object(server.CHATGPT,'explain',return_value=json.dumps(result)):
            code,body=self.request('/api/advisor',self.payload());self.assertEqual(code,400);self.assertIn(b'protected',body)

if __name__=='__main__': unittest.main()
