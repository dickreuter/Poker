cursor = L.mongodb.games.aggregate([
        { "$unwind" : "$rounds"},
        { "$match": {"Template": {"$regex":'.*'}}},
        { "$group": {
             "_id": {"GameID": "$GameID", "gameStage": "$rounds.round_values.gameStage"},
             "lastDecision": {"$last": "$rounds.round_values.decision"},
             "FinalOutcome": { "$last": "$FinalOutcome" },
             "FinalFundsChange": { "$last": "$FinalFundsChange" },
           }
         },
        { "$group": {
             "_id": {"ld": "$lastDecision", "fa": "$FinalOutcome","gs": "$_id.gameStage"},
             "Total": {"$sum": "$FinalFundsChange"}}}
        ])

cursor = L.mongodb.games.aggregate([
        { "$unwind" : "$rounds"},
        { "$match": {"Template": {"$regex":'.*'}}},
        { "$group": {
             "_id": {"GameID": "$GameID", "gameStage": "$rounds.round_values.gameStage"},
             "lastDecision": {"$last": "$rounds.round_values.decision"},
             "FinalOutcome": { "$last": "$FinalOutcome" },
             "FinalFundsChange": { "$last": "$FinalFundsChange" },
           }
         },
        { "$group": {
             "_id": {"ld": "$lastDecision", "fa": "$FinalOutcome","gs": "$_id.gameStage"},
             "Total": {"$sum": "$FinalFundsChange"}}}
        ])


cursor = L.mongodb.games.aggregate([
        { "$unwind" : "$rounds"},
        {"$match": {"Template": {"$regex":'.*'},
                    "GameID": "680179745"}},
        { "$group": {
             "_id": {"GameID": "$GameID", "gameStage": "$rounds.round_values.gameStage"},
             "lastDecision": {"$last": "$rounds.round_values.decision"},
             "FinalOutcome": { "$last": "$FinalOutcome" },
             "FinalFundsChange": { "$last": "$FinalFundsChange" },
           }
         }
        ])

cursor = L.mongodb.games.aggregate([
        { "$unwind" : "$rounds"},
        {"$match": {"Template": {"$regex":'.*'},
                    "GameID": "680179745"}},
        { "$group": {
             "_id": {"GameID": "$GameID", "gameStage": "$rounds.round_values.gameStage"},
             "lastDecision": {"$last": "$rounds.round_values.decision"},
             "FinalOutcome": { "$last": "$FinalOutcome" },
             "FinalFundsChange": { "$last": "$FinalFundsChange" },
           }
         }
        ])

cursor = L.mongodb.games.aggregate([
        { "$unwind" : "$rounds"},
        {"$match": {"Template": {"$regex":'.*'},
                    "GameID": "680179745"}}
        ])

cursor = L.mongodb.games.find({"GameID": "680179745"})
for document in cursor:
    print(document)
list(cursor)
dd = pd.DataFrame(list(cursor))

db.orders.aggregate([
    {
      $lookup:
        {
          from: "inventory",
          localField: "item",
          foreignField: "sku",
          as: "inventory_docs"
        }
   }
])

cursor = L.mongodb.games.aggregate([
        {"$unwind" : "$rounds"},
        {"$match": {"Template": {"$regex":'.*'},
                    "GameID": "680179745",
                    "rounds.round_values.gameStage": "PreFlop"}},
        {"$project": {
        "assumedPlayers": "$rounds.round_values.assumedPlayers",
        "coveredCardHolders": "$rounds.round_values.coveredCardHolders",
        "equity": "$rounds.round_values.equity",
        "isHeadsUp": "$rounds.round_values.isHeadsUp",
        "playersAhead": "$rounds.round_values.playersAhead",
        "playersBehind": "$rounds.round_values.playersBehind",
        "minCall": "$rounds.round_values.minCall",
        "minBet": "$rounds.round_values.minBet",
        "totalPotValue": "$rounds.round_values.totalPotValue",
        "_id": 0}}
        ])

list(cursor)
