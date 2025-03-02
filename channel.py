from flask import Flask, request, render_template, jsonify, session
import uuid
import json
import requests
from flask_cors import CORS
from datetime import datetime
import random
from better_profanity import profanity 

# Class-based application configuration
class ConfigClass(object):
    """ Flask application config """
    SECRET_KEY = '191996'

# Create Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.config.from_object(__name__ + '.ConfigClass')  # configuration
app.app_context().push()  # create an app context before initializing db

HUB_URL = 'http://localhost:5555'
HUB_AUTHKEY = '1234567890'
CHANNEL_AUTHKEY = '0987654321'
CHANNEL_NAME = "Coxi Movies"
CHANNEL_ENDPOINT = "http://localhost:5001"
CHANNEL_FILE = 'messages.json'
CHANNEL_TYPE_OF_SERVICE = 'aiweb24:chat'

profanity.load_censor_words()  # Load the default profanity list

@app.cli.command('register')
def register_command():
    global CHANNEL_AUTHKEY, CHANNEL_NAME, CHANNEL_ENDPOINT
    response = requests.post(HUB_URL + '/channels', headers={'Authorization': 'authkey ' + HUB_AUTHKEY},
                             data=json.dumps({
                                "name": CHANNEL_NAME,
                                "endpoint": CHANNEL_ENDPOINT,
                                "authkey": CHANNEL_AUTHKEY,
                                "type_of_service": CHANNEL_TYPE_OF_SERVICE,
                             }))
    if response.status_code != 200:
        print("Error creating channel: "+str(response.status_code))
        print(response.text)
        return

def check_authorization(request):
    global CHANNEL_AUTHKEY
    if 'Authorization' not in request.headers:
        return False
    if request.headers['Authorization'] != 'authkey ' + CHANNEL_AUTHKEY:
        return False
    return True

## BOT ##########

def get_auto_response():
    """Fetches a random response from responses.txt"""
    try:
        with open("responses.txt", "r") as file:
            responses = file.readlines()
        return random.choice(responses).strip()
    except FileNotFoundError:
        return "I'm here to help!"

# Profanity Response 

def get_profanity_response():
    """Fetches a random response from profanity_responses.txt for messages containing profanity"""
    try:
        with open("profanity_responses.txt", "r") as file:
            responses = file.readlines()
        return random.choice(responses).strip()
    except FileNotFoundError:
        return "Please watch your language!"
    

#############


@app.route('/health', methods=['GET'])
def health_check():
    global CHANNEL_NAME
    if not check_authorization(request):
        return "Invalid authorization", 400
    return jsonify({'name':CHANNEL_NAME}), 200

@app.route('/', methods=['GET'])
def home_page():
    if not check_authorization(request):
        return "Invalid authorization", 400

    messages = read_messages()
    filter_type = request.args.get('filter')

    if filter_type == 'oldest':
        messages = list(reversed(messages))
    elif filter_type == 'popularity':
        messages = sorted(messages, key=lambda x: x.get('likes', 0), reverse=True)

    #Create a welcome message 
    welcome_message = {
            'id': '000',
            'content': 'Welcome to Coxi Movies! Tell us about your favorite coxi related movie.',
            'sender': 'Welcome Message',
            'timestamp': datetime.now().isoformat(),
            'category': None,
            'movie': None,
            'likes': 0,
            'bot_response': ''
        }

    # appending the welcome message
    messages = [welcome_message] + messages

    return jsonify(messages[:10])

@app.route('/', methods=['POST'])
def send_message():
    if not check_authorization(request):
        return "Invalid authorization", 400

    message = request.json
    message_id = str(uuid.uuid4())
    messages = read_messages()

    # Generate random sender if not provided
    message_sender = message.get('sender', '').strip()
    if not message_sender:
        message_sender = random.choice(['Anonymous', 'User']) + str(random.randint(1, 999))

    try:
        timestamp_obj = datetime.fromisoformat(message['timestamp'])
        formatted_timestamp = timestamp_obj.strftime('%d %b %H:%M')
    except ValueError:
        formatted_timestamp = datetime.now().strftime('%d %b %H:%M')

    # Filter the content using better_profanity
    filtered_content = profanity.censor(message['content'])

    # Check if profanity was detected
    if filtered_content != message['content']:
        # If profanity is found, pick a response from the profanity file
        bot_response = get_profanity_response()
    else:
        # Otherwise, use the normal response
        bot_response = get_auto_response()

     # 1) Insert the user’s message
    user_message = {
        'id': message_id,
        'content': filtered_content,
        'sender': message_sender,
        'timestamp': formatted_timestamp,
        'category': message.get('category', 'Other'),
        'movie': message.get('movie', 'Unknown'),
        'likes': message.get('likes', 0),
        'bot_response': bot_response
    }
    messages.insert(0, user_message)

    # 2) Insert bot message
    bot_message = {
        'id': str(uuid.uuid4()),
        'content': bot_response,            # The content is the bot's reply
        'sender': 'BOT',                    # Mark the sender as BOT
        'timestamp': datetime.now().strftime('%d %b %H:%M'),
        'category': None,
        'movie': None,
        'likes': 0,
        'bot_response': ''                  # Usually empty or None for the bot itself
    }

    messages.insert(1, bot_message)

    save_messages(messages)
    return "OK", 200

@app.route('/like_message/<message_id>', methods=['POST'])
def like_message(message_id):
    messages = read_messages()
    message_found = False

    for message in messages:
        if message['id'] == message_id:
            message_found = True
            if message.get('likes') is None:
                message['likes'] = 0
            message['likes'] += 1
            break

    if not message_found:
        return jsonify({'success': False, 'error': 'Message ID not found'}), 404

    save_messages(messages)
    return jsonify({'success': True, 'likes': message['likes']})

@app.route('/reset_channel', methods=['POST'])
def reset_channel():
    if not check_authorization(request):
        return "Invalid authorization", 400

    save_messages([])  # Clear all messages
    return jsonify({'success': True, 'message': 'Channel has been reset!'}), 200

def read_messages():
    global CHANNEL_FILE
    try:
        with open(CHANNEL_FILE, 'r') as f:
            messages = json.load(f)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        messages = []
    return messages[:10]

def save_messages(messages):
    global CHANNEL_FILE
    ## Only save and serve the last 3 messages ############################
    messages = messages[:10]
    with open(CHANNEL_FILE, 'w') as f:
        json.dump(messages, f)

if __name__ == '__main__':
    print("Registered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule}")

    app.run(port=5001, debug=True)
