class AgregateData(object):
    def __init__(self, connection='mongodb://guest:donald@52.201.173.151:27017/POKER'):
        self.mongoclient = MongoClient('mongodb://guest:donald@52.201.173.151:27017/POKER')
        self.mongodb = self.mongoclient.POKER

    def get_my_gameStage_data(self, gameStage, GameID):
        cursor = self.mongodb.games.aggregate([
            {"$unwind" : "$rounds"},
            {"$match": {"GameID": GameID,
                        "rounds.round_values.gameStage": gameStage,
                        "Template": "Vid PP Supersonic 2 5"}},
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
        gameStage_data = pd.DataFrame(list(cursor))
        gameStage_data.columns = [str(gameStage)+"_"+ str(col) for col in gameStage_data.columns]
        return gameStage_data

    def get_GameID_rounds_count(self,GameID):
        cursor = self.mongodb.games.aggregate([
                        {"$unwind" : "$rounds"},
                        {"$match": {"GameID": GameID,
                                    "Template": "Vid PP Supersonic 2 5"}},
                        {"$group": {
                        "max_rounds":{"$max" : "$rounds.round_number"},
                        "_id": 0}}
                        ])
        return float(pd.DataFrame(list(cursor))["max_rounds"])


    def get_my_gameStages_data(self,GameID):
        Game_rounds_count = self.get_GameID_rounds_count(GameID)

        if Game_rounds_count >=0:
            PrefFlop_data = self.get_my_gameStage_data("PreFlop", GameID)
            temp_gamstage_data = PrefFlop_data.copy()
            temp_gamstage_data.ix[0,] = -1
            PreFlop_var_names = list(PrefFlop_data.columns.values)
            Flop_var_names = [w.replace('PreFlop', 'Flop') for w in PreFlop_var_names]
            Turn_var_names = [w.replace('PreFlop', 'Turn') for w in PreFlop_var_names]
            River_var_names = [w.replace('PreFlop', 'River') for w in PreFlop_var_names]

        if Game_rounds_count >=1:
            Flop_data = self.get_my_gameStage_data("Flop", GameID)
        else:
            Flop_data = temp_gamstage_data.copy()
            Flop_data.columns = Flop_var_names

        if Game_rounds_count >=2:
            Turn_data = self.get_my_gameStage_data("Turn", GameID)
        else:
            Turn_data = temp_gamstage_data.copy()
            Turn_data.columns = Turn_var_names

        if Game_rounds_count >=3:
            River_data = self.get_my_gameStage_data("River", GameID)
        else:
            River_data = temp_gamstage_data.copy()
            River_data.columns = River_var_names

        gameStages_data = pd.concat([PrefFlop_data, Flop_data,Turn_data,River_data], axis=1)

        return gameStages_data


