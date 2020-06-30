# notes-python
Python implementation of the serverless-stack tutorial.

https://serverless-stack.com/#table-of-contents



# Running the Tests Locally
Note: There are hardcoded noteId's in the update-event, get-event, and delete-event .json files. These IDs will need to be valid NoteIds in order for those functions to work.

DynamoDB Tablename: notes-python-example-database
https://console.aws.amazon.com/dynamodb/home?region=us-east-1#tables:selected=notes-python-example-database;tab=overview
This infrastructure item is not IAC'd so if you notice that it is not present, it will likely need to be recreated.
```
serverless invoke local --function create --path mocks/create-event.json
serverless invoke local --function update --path mocks/update-event.json
serverless invoke local --function get --path mocks/get-event.json
serverless invoke local --function delete --path mocks/delete-event.json
serverless invoke local --function list --path mocks/list-event.json
```

# Serverless Websocket API
```javascript
// update the user info 
// IMPORTANT: the user info must be updated before any other requests are made, becasue everything is tied to the round
{"action": "updateUserInfo", "roundID": "your_round_id", "username": "your_user_name"}
// does not broadcast anything, updates the user info in the db


// create a new question
{"action": "createQuestion", "question": "your question here"}
// does not broadcast anything, but adds a new question to the db

// start the game
{"action": "startGame"}
// if the numQuestions == numUsers,
// picks a user randomly to send a question to, same as "setAnswerer" action
// else, broadcasts error to user who called "startGame"
{"type": "startError", "waitingFor": "1"}


// get all users who haven't answered a question yet
{"action": "getPotentialAnswerers"} 
// broadcasts to all users in round:
{"type": "pickAnswerer", "options": [user list]}


// set the next answerer
{"action": "setAnswerer", "answerer": "Chad"}
// broadcasts to user defined by "answerer" above
{"type": "pickQuestion", "questionIDs": ["qid1", "qid2", ...]}
// broadcasts to all users EXCEPT "answerer". 
// "username" is the user who sent the "setAnswerer" call
{"type": "nextAnswerer", "username": "otherUser", "answerer": "Chad"}


// ask a question to the round. Should be called on clicking the question tile
{"action": "askQuestion", "questionID": "3"}
// broadcasts to all users in round.
// "username" is the user who sent the "askQuestion" call
{"type": "question", "username": "otherUser", "question": "mockCreateContent"}
```


# Deploying
`AWS_PROFILE=pg serverless deploy`

Shoutout to 2020 Group A Interns: Kyle Brainard, Kate Ryan, and Will Pasley for the blazing the way and doing the initial javascript to python conversion.
