import itertools
import json
import random
import unittest
from unittest.mock import patch
from core import parse_inventory, solve, card_cost, validate_inventory


def player(i, **changes):
    p = dict(id=str(i), name=f'Fictional {i}', rating=75, value=100,
             nation=f'N{i % 3}', league=f'L{i % 2}', club=f'C{i % 4}',
             position='CM', rare=False, untradeable=False, duplicate=False,
             protected=False, startingXI=False)
    p.update(changes)
    return p


class ImportTests(unittest.TestCase):
    def test_json_defaults(self):
        p = parse_inventory('[{"id":"a","name":"A","rating":75}]')[0]
        self.assertFalse(p['protected'])
        self.assertEqual(p['value'], 0)

    def test_csv_quoted_boolean(self):
        p = parse_inventory('id,name,rating,duplicate,protected\na,"A, B",81,true,0\n', 'csv')[0]
        self.assertEqual(p['name'], 'A, B')
        self.assertTrue(p['duplicate'])
        self.assertFalse(p['protected'])

    def test_invalid_inputs(self):
        bad = ['{}', '[]', '[null]', '{', '[{"id":"a","name":"A","rating":true}]',
               '[{"id":"a","name":"A","rating":100}]',
               '[{"id":"a","name":"A","rating":75,"protected":"false"}]',
               '[{"id":"a","id":"b","name":"A","rating":75}]',
               '[{"id":"a","name":"A","rating":75,"chemistry":2}]']
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_inventory(raw)
        with self.assertRaises(ValueError):
            parse_inventory(json.dumps([player(1), player(1)]))
        with self.assertRaises(ValueError):
            parse_inventory(json.dumps([player(i) for i in range(151)]))
        for raw in ('id,name,rating\na,A,75,extra', 'id,name,rating\na,A', 'id,id,name,rating\na,b,A,75', 'id,name,rating,rare\na,A,75,maybe', 'id,name,rating\na,"bad,75'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_inventory(raw, 'csv')


class SolverTests(unittest.TestCase):
    def test_protected_and_starting_xi(self):
        players = [player(1, protected=True, value=0), player(2, startingXI=True, value=0), player(3), player(4), player(5)]
        result = solve(players, {'squadSize': 2, 'protectedIds': ['3']})
        self.assertEqual(result['status'], 'optimal')
        self.assertEqual({p['id'] for p in result['squad']}, {'4', '5'})

    def test_duplicate_and_untradeable_preference(self):
        result = solve([player(1), player(2, untradeable=True), player(3, duplicate=True)], {'squadSize': 2})
        self.assertEqual({p['id'] for p in result['squad']}, {'2', '3'})

    def test_constraints(self):
        players = [player(i, rating=80+i, rare=i % 2 == 0) for i in range(8)]
        result = solve(players, dict(squadSize=3, minAverageRating=83, minRare=2, minLeagues=2, maxLeagues=2, minNations=2, maxNations=3, maxSameClub=1, budget=300))
        self.assertEqual(result['status'], 'optimal')
        self.assertGreaterEqual(result['metrics']['averageRating'], 83)
        self.assertGreaterEqual(result['metrics']['rare'], 2)
        self.assertEqual(len({p['club'] for p in result['squad']}), 3)

    def test_infeasible_not_timeout(self):
        result = solve([player(1)], {'squadSize': 2})
        self.assertEqual(result['status'], 'infeasible')
        self.assertEqual(result['squad'], [])
        self.assertEqual(solve([player(1)], {'squadSize': 1, 'minAverageRating': 99})['status'], 'infeasible')
        self.assertEqual(solve([player(1)], {'squadSize': 1, 'budget': 0})['status'], 'infeasible')

    def test_timeout_is_not_infeasible(self):
        result = solve([player(1)], {'squadSize': 1}, time_limit=0)
        self.assertEqual(result['status'], 'timeout')

    def test_feasible_timeout_keeps_candidate(self):
        # Deadline starts at zero; first leaf is found before the next branch times out.
        ticks = iter([0, 0, 0, 0, 3])
        with patch('core.time.monotonic', side_effect=lambda: next(ticks, 3)):
            result = solve([player(i) for i in range(5)], {'squadSize': 2}, time_limit=2)
        self.assertEqual(result['status'], 'feasible')
        self.assertEqual(len(result['squad']), 2)

    def test_missing_metadata_cannot_satisfy_constraints(self):
        players = parse_inventory('[{"id":"a","name":"A","rating":75}]')
        with self.assertRaisesRegex(ValueError, 'Missing league metadata'):
            solve(players, {'squadSize': 1, 'minLeagues': 1})

    def test_invalid_constraints(self):
        for c in ({'chemistry': 0}, {'squadSize': True}, {'minAverageRating': float('nan')}, {'budget': -1}, {'protectedIds': ['missing']}, {'minRare': 12}, {'positions': []}):
            with self.subTest(c=c), self.assertRaises(ValueError):
                solve([player(1)], c)

    def test_same_player_id_cannot_be_selected_twice(self):
        players = [player(1, playerId='footballer-a'), player(2, playerId='footballer-a'), player(3, playerId='footballer-b')]
        result = solve(players, {'squadSize': 2})
        self.assertEqual(result['status'], 'optimal')
        self.assertEqual(len({p['playerId'] for p in result['squad']}), 2)
        self.assertEqual(solve(players[:2], {'squadSize': 2})['status'], 'infeasible')

    def test_same_name_fallback_and_mixed_metadata(self):
        a, b = player(1, name=' ALex   SMITH '), player(2, name='alex smith')
        self.assertEqual(solve([a, b], {'squadSize': 2})['status'], 'infeasible')
        a['playerId'] = '123'
        self.assertEqual(solve([a, b], {'squadSize': 2})['status'], 'infeasible')
        b['playerId'] = '456'
        self.assertEqual(solve([a, b], {'squadSize': 2})['status'], 'optimal')

    def test_known_item_score_constraint(self):
        players = [player(1, itemScore=4), player(2, itemScore=8), player(3, itemScore=12)]
        result = solve(players, {'squadSize': 2, 'minTotalItemScore': 20})
        self.assertEqual(result['status'], 'optimal')
        self.assertEqual(result['metrics']['totalItemScore'], 20)
        self.assertTrue(result['metrics']['itemScoreComplete'])
        self.assertEqual(solve(players, {'squadSize': 2, 'minTotalItemScore': 21})['status'], 'infeasible')
        with self.assertRaisesRegex(ValueError, 'Missing itemScore'):
            solve([player(1)], {'squadSize': 1, 'minTotalItemScore': 1})
        for score in (-1, True, 1.5, '8'):
            with self.assertRaises(ValueError):
                validate_inventory([player(1, itemScore=score)])
        parsed = parse_inventory('id,name,rating,itemScore,playerId\na,A,75,8,123\n', 'csv')
        self.assertEqual(parsed[0]['itemScore'], 8)
        self.assertEqual(parsed[0]['playerId'], '123')

    def test_determinism_and_no_mutation(self):
        players = [player(i) for i in range(8)]
        before = json.dumps(players)
        self.assertEqual(solve(players, {'squadSize': 3}), solve(players, {'squadSize': 3}))
        self.assertEqual(json.dumps(players), before)

    def test_random_small_against_brute_force(self):
        rng = random.Random(112)
        for trial in range(40):
            players = [player(i, rating=rng.randint(70, 85), value=rng.randint(0, 1000), rare=rng.choice([True, False]), duplicate=rng.choice([True, False])) for i in range(9)]
            c = dict(squadSize=3, minAverageRating=rng.randint(74, 82), minRare=1, minLeagues=2, maxNations=2, maxSameClub=1, budget=1800)
            valid = []
            for squad in itertools.combinations(players, 3):
                if (sum(p['rating'] for p in squad) >= c['minAverageRating']*3 and sum(p['rare'] for p in squad) >= 1
                    and len({p['league'] for p in squad}) >= 2 and len({p['nation'] for p in squad}) <= 2
                    and len({p['club'] for p in squad}) == 3 and sum(p['value'] for p in squad) <= 1800):
                    valid.append(sum(card_cost(p) for p in squad))
            result = solve(players, c)
            self.assertEqual(result['status'], 'optimal' if valid else 'infeasible', trial)
            if valid:
                self.assertEqual(result['metrics']['objective'], min(valid), trial)


if __name__ == '__main__':
    unittest.main()
