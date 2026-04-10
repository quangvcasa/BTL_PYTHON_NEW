from flask import Flask, redirect, url_for
app = Flask(__name__)

@app.route('/')
def index():
    return "Hello"

@app.route('/redirect_400')
def redirect_400():
    return redirect(url_for('index')), 400

if __name__ == "__main__":
    with app.test_client() as c:
        resp = c.get('/redirect_400')
        print(f"Status: {resp.status_code}")
        print(f"Headers Location: {resp.headers.get('Location')}")
        print(f"Data: {resp.data}")
