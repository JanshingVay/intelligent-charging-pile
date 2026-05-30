from app import app

c = app.test_client()
c.post('/api/login', json={'user_id': 'user1', 'password': '123456'})

print("=== Simulating rapid fast charge submissions ===")

for i in range(1, 13):
    r = c.post('/api/charge/request', json={'charge_mode': 'Fast', 'need_power': 30.0})
    
# Check final state
r = c.get('/api/waiting-area')
wa = r.get_json()
print(f"Waiting area: {wa['current_count']} cars")

r = c.get('/api/charging-area')
piles = r.get_json()['piles']
for p in piles:
    qv = [q['queue_number'] for q in p.get('queue', [])]
    ch = p['current_charging']['queue_number'] if p['current_charging'] else 'None'
    print(f"  {p['pile_id']}: status={p['status']}, charging={ch}, queue({len(qv)})={qv}")

# The key assertion: waiting area should NOT be 0
assert wa['current_count'] > 0, f"BUG: Waiting area cleared! Should NOT be 0."
print(f"\nPASSED: Waiting area has {wa['current_count']} cars (not cleared!)")
