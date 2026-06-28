from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from logging.config import dictConfig
from app.config import Config, LOGGING

dictConfig(LOGGING)

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

@app.route('/')
def hello_world():
    return 'Hello World!'
