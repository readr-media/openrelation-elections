from flask import Flask
import os
from special_municipality import gen_special_municipality_polling
app = Flask(__name__)


@app.route("/special_municipality", methods=['GET'])
def municipality():
        gen_special_municipality_polling()
        return 'done'


@app.route("/")
def healthcheck():
    return "ok"


if __name__ == "__main__":
    app.run()
