"""Local-only planning engine; arithmetic rating is NOT EA squad-rating validation."""
import csv
import io
import json
import math
import time
from collections import Counter

FIELDS = {'id', 'name', 'rating', 'nation', 'league', 'club', 'position', 'rare',
          'untradeable', 'duplicate', 'protected', 'startingXI', 'value', 'playerId', 'itemScore'}
BOOL_FIELDS = {'rare', 'untradeable', 'duplicate', 'protected', 'startingXI'}
CONSTRAINTS = {'squadSize', 'minAverageRating', 'minRare', 'minLeagues', 'maxLeagues',
               'minNations', 'maxNations', 'maxSameClub', 'budget', 'protectedIds', 'minTotalItemScore'}


def _int(value, label, low, high, csv_mode=False):
    if csv_mode and isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            raise ValueError(f'{label} must be an integer.') from None
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer between {low} and {high}.')
    return value


def validate_inventory(rows, csv_mode=False):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 150:
        raise ValueError('Inventory must be a list of 1–150 player cards.')
    result, seen = [], set()
    for i, row in enumerate(rows, 1):
        prefix = f'Player {i}'
        if not isinstance(row, dict):
            raise ValueError(f'{prefix} must be an object.')
        if set(row) - FIELDS:
            raise ValueError(f'{prefix}: unsupported fields: {", ".join(sorted(str(x) for x in set(row) - FIELDS))}.')
        p = {}
        for key in ('id', 'name', 'nation', 'league', 'club', 'position'):
            value = row.get(key, '' if key in ('id', 'name') else 'Unknown')
            if not isinstance(value, str) or not value.strip() or len(value) > 120:
                raise ValueError(f'{prefix}: {key} must be nonempty text, at most 120 characters.')
            p[key] = value.strip()
        if p['id'] in seen:
            raise ValueError(f'Duplicate card id: {p["id"]}. Every card needs a unique id.')
        seen.add(p['id'])
        p['rating'] = _int(row.get('rating'), f'{prefix} rating', 1, 99, csv_mode)
        p['value'] = _int(row.get('value', 0), f'{prefix} value', 0, 100_000_000, csv_mode)
        for key in BOOL_FIELDS:
            value = row.get(key, False)
            if csv_mode and isinstance(value, str):
                if value.strip().lower() not in ('true', 'false', '1', '0', ''):
                    raise ValueError(f'{prefix}: {key} must be true or false.')
                value = value.strip().lower() in ('true', '1')
            if type(value) is not bool:
                raise ValueError(f'{prefix}: {key} must be a boolean.')
            p[key] = value
        if 'playerId' in row and row['playerId'] not in (None, ''):
            value = row['playerId']
            if not isinstance(value, str) or not value.strip() or len(value) > 120:
                raise ValueError(f'{prefix}: playerId must be nonempty text, at most 120 characters.')
            p['playerId'] = value.strip()
        if 'itemScore' in row and row['itemScore'] not in (None, ''):
            p['itemScore'] = _int(row['itemScore'], f'{prefix} itemScore', 0, 100_000_000, csv_mode)
        result.append(p)
    return result


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}.')
        result[key] = value
    return result


def parse_inventory(text, format='json'):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 1_000_000:
        raise ValueError('Inventory must be text under 1 MB.')
    if format == 'json':
        try:
            rows = json.loads(text, object_pairs_hook=_json_object)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError(f'Invalid JSON: {exc}') from None
        return validate_inventory(rows)
    if format == 'csv':
        try:
            reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), strict=True)
            headers = reader.fieldnames
            if not headers or len(set(headers)) != len(headers):
                raise ValueError('CSV requires unique column headers.')
            rows = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in rows):
                raise ValueError('CSV rows must have the same number of fields as the header.')
            return validate_inventory(rows, csv_mode=True)
        except csv.Error as exc:
            raise ValueError(f'Invalid CSV: {exc}') from None
    raise ValueError('Supported import formats are json and csv.')


def validate_constraints(raw):
    if not isinstance(raw, dict):
        raise ValueError('Constraints must be an object.')
    unsupported = set(raw) - CONSTRAINTS
    if unsupported:
        raise ValueError('Unsupported constraints: ' + ', '.join(sorted(str(x) for x in unsupported)) + '. Chemistry, positions and EA squad rating are not implemented.')
    c = {'squadSize': 11, 'minAverageRating': 0, 'minRare': 0, 'minLeagues': 0,
         'maxLeagues': 11, 'minNations': 0, 'maxNations': 11, 'maxSameClub': 11,
         'budget': 1_100_000_000, 'protectedIds': [], 'minTotalItemScore': 0}
    c.update(raw)
    for key in ('squadSize', 'minRare', 'minLeagues', 'maxLeagues', 'minNations', 'maxNations', 'maxSameClub'):
        c[key] = _int(c[key], key, 1 if key in ('squadSize', 'maxSameClub') else 0, 11)
    c['budget'] = _int(c['budget'], 'budget', 0, 1_100_000_000)
    c['minTotalItemScore'] = _int(c['minTotalItemScore'], 'minTotalItemScore', 0, 1_100_000_000)
    rating = c['minAverageRating']
    if type(rating) not in (int, float) or not math.isfinite(rating) or not 0 <= rating <= 99:
        raise ValueError('minAverageRating must be a finite number from 0 to 99.')
    if not isinstance(c['protectedIds'], list) or any(not isinstance(x, str) for x in c['protectedIds']):
        raise ValueError('protectedIds must be a list of card ids.')
    if len(c['protectedIds']) > 150:
        raise ValueError('At most 150 protectedIds are allowed.')
    return c


def player_identity(p):
    return ('id', p['playerId']) if p.get('playerId') else ('name', ' '.join(p['name'].casefold().split()))


def same_player(a, b):
    if a.get('playerId') and b.get('playerId'):
        return a['playerId'] == b['playerId']
    return ' '.join(a['name'].casefold().split()) == ' '.join(b['name'].casefold().split())


def card_cost(p):
    """Heuristic conservation score, not market price or financial advice."""
    factor = 15 if p['duplicate'] else 65 if p['untradeable'] else 100
    return p['value'] * factor + max(0, p['rating'] - 75) ** 2 * 10000


def squad_metrics(squad):
    return {'totalItemScore': sum(p.get('itemScore', 0) for p in squad),
            'itemScoreComplete': all('itemScore' in p for p in squad),
            'averageRating': sum(p['rating'] for p in squad) / len(squad) if squad else 0,
            'totalValue': sum(p['value'] for p in squad), 'rare': sum(p['rare'] for p in squad),
            'leagues': len({p['league'] for p in squad}), 'nations': len({p['nation'] for p in squad}),
            'duplicates': sum(p['duplicate'] for p in squad),
            'untradeables': sum(p['untradeable'] for p in squad),
            'objective': sum(card_cost(p) for p in squad)}


def solve(players, constraints, *, time_limit=2.0):
    players = validate_inventory(players)
    c = validate_constraints(constraints)
    if not isinstance(time_limit, (int, float)) or not math.isfinite(time_limit) or time_limit < 0:
        raise ValueError('time_limit must be a nonnegative finite number.')
    unknown = set(c['protectedIds']) - {p['id'] for p in players}
    if unknown:
        raise ValueError('Unknown protected card ids: ' + ', '.join(sorted(unknown)))
    pool = sorted((p for p in players if not p['protected'] and not p['startingXI'] and p['id'] not in c['protectedIds']), key=lambda p: (card_cost(p), p['id']))
    n, size = len(pool), c['squadSize']
    for field, active in (
        ('league', c['minLeagues'] > 0 or c['maxLeagues'] < size),
        ('nation', c['minNations'] > 0 or c['maxNations'] < size),
        ('club', c['maxSameClub'] < size),
    ):
        if active and any(p[field] == 'Unknown' for p in pool):
            raise ValueError(f'Missing {field} metadata: provide it for every eligible card before using {field} constraints.')
    if c['minTotalItemScore'] > 0 and any('itemScore' not in p for p in pool):
        raise ValueError('Missing itemScore metadata: provide a known item score for every eligible card before using minTotalItemScore.')
    costs = [card_cost(p) for p in pool]
    prefix = [0]
    for cost in costs:
        prefix.append(prefix[-1] + cost)
    deadline = time.monotonic() + time_limit
    best, best_cost, explored, timed_out = None, math.inf, 0, False
    target = c['minAverageRating'] * size
    chosen, clubs, leagues, nations = [], Counter(), Counter(), Counter()
    identities = set()

    def search(start, cost, rating, rare, value, item_score):
        nonlocal best, best_cost, explored, timed_out
        explored += 1
        if time.monotonic() >= deadline:
            timed_out = True
            return
        need = size - len(chosen)
        if n - start < need or value > c['budget'] or len(leagues) > c['maxLeagues'] or len(nations) > c['maxNations']:
            return
        if len(leagues) + need < c['minLeagues'] or len(nations) + need < c['minNations'] or rare + need < c['minRare']:
            return
        if cost + prefix[start + need] - prefix[start] >= best_cost:
            return
        if need == 0:
            if item_score >= c['minTotalItemScore'] and rating + 1e-9 >= target and rare >= c['minRare'] and len(leagues) >= c['minLeagues'] and len(nations) >= c['minNations']:
                best, best_cost = list(chosen), cost
            return
        # Safe optimistic bound; unlike rounded squad rating, this uses only arithmetic.
        if rating + sum(sorted((p['rating'] for p in pool[start:]), reverse=True)[:need]) + 1e-9 < target:
            return
        if item_score + sum(sorted((p.get('itemScore', 0) for p in pool[start:]), reverse=True)[:need]) < c['minTotalItemScore']:
            return
        for index in range(start, n - need + 1):
            p = pool[index]
            identity = player_identity(p)
            if (identity in identities or any(same_player(p, existing) for existing in chosen)) or cost + costs[index] >= best_cost or clubs[p['club']] >= c['maxSameClub']:
                continue
            chosen.append(p)
            identities.add(identity)
            clubs[p['club']] += 1
            leagues[p['league']] += 1
            nations[p['nation']] += 1
            search(index + 1, cost + costs[index], rating + p['rating'], rare + p['rare'], value + p['value'], item_score + p.get('itemScore', 0))
            chosen.pop()
            identities.remove(identity)
            for counter, key in ((clubs, p['club']), (leagues, p['league']), (nations, p['nation'])):
                counter[key] -= 1
                if not counter[key]:
                    del counter[key]
            if timed_out:
                return

    search(0, 0, 0, 0, 0, 0)
    status = ('feasible' if best else 'timeout') if timed_out else ('optimal' if best else 'infeasible')
    explanation = {
        'optimal': 'Lowest conservation-score squad proven for the supported simplified constraints.',
        'feasible': 'Valid for supported simplified constraints; search timed out, so optimality is not proven.',
        'timeout': 'Search timed out without finding a squad. This does not prove the challenge is impossible.',
        'infeasible': 'Exhaustive search found no squad satisfying the supported simplified constraints and protections.',
    }[status]
    return {'status': status, 'squad': best or [], 'metrics': squad_metrics(best or []),
            'explanation': explanation, 'explored': explored, 'ratingMode': 'simplified_arithmetic_average',
            'warnings': ['Planning only: arithmetic average is not EA squad rating. Chemistry, formation/position and card eligibility are not validated. Same-footballer uniqueness compares playerId when both cards have one, otherwise normalized name; supply consistent playerId on all versions to avoid aliases or namesakes. Item score is user-entered, not an EA formula. Verify in-game before submitting.',
                         'Conservation score is a heuristic, not coins: value × (15 if duplicate, else 65 if untradeable, else 100) + 10000 × max(rating−75, 0)².']}
