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
// get all users who haven't answered a question yet
{"action": "getPotentialAnswerers"} 
// broadcasts to all users in round:
{"type": "pickAnswerer", "options": [user list]}


// set the next answerer
{"action": "setAnswerer", "answerer": "Chad"}
// broadcasts to user defined by "answerer" above
{"type": "pickQuestion", "question_ids": []}
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
