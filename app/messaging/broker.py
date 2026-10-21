import os

from dotenv import load_dotenv
from faststream.rabbit import RabbitBroker

load_dotenv()

RABBITMQ_URL = os.environ["RABBITMQ_URL"]

broker = RabbitBroker(RABBITMQ_URL)
