from app import app
import re

app.config['WTF_CSRF_ENABLED'] = True  # Ensure CSRF is enabled in tests
client = app.test_client()

# Test 1: GET request (should pass)
resp_get = client.get('/login')
print(f"GET /login -> Status: {resp_get.status_code}")
html = resp_get.data.decode('utf-8')

# Extract CSRF token
match = re.search(r'name="csrf_token" value="(.*?)"', html)
if not match:
    print("WARNING: CSRF token not found in /login HTML!")
    csrf_token = ""
else:
    csrf_token = match.group(1)
    print("Found CSRF token in HTML.")

# Test 2: POST request WITHOUT token
resp_post_no_token = client.post('/login', data={'username': 'admin', 'password': 'password'})
print(f"POST /login (NO token) -> Status: {resp_post_no_token.status_code}")

# Test 3: POST request WITH valid token
# For WTF_CSRF_ENABLED, test client needs to handle sessions properly if we send real requests.
# Flask-WTF stores the CSRF secret in the session, so we need to reuse the same client that made the GET request.

resp_post_token = client.post('/login', data={
    'username': 'admin',
    'password': 'password',
    'csrf_token': csrf_token
})
print(f"POST /login (WITH token) -> Status: {resp_post_token.status_code}")

