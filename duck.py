import requests
import json
import os


class DuckManager:
    def __init__(self):
        # This initializes the data object containing all the duck information
        # if internet is not available or for some reason the api is down it defaults to a local copy
        try:
            data = requests.get(
                "https://duckland-production.up.railway.app/ducks").json()
            with open("cache.json", "w") as file:
                json.dump(data, file, indent=4)
        except:
            if not os.path.isfile("cache.json"):
                # here we're checking to see if the file exists and creating an empty one if it doesnt
                with open("cache.json", "w") as file:
                    pass
            with open("cache.json", "r") as file:
                data = file.read()
        self.data = data
        self.duck_list = []

    def create_duck_list(self, id: list[str] | str | None = []):
        """Creates and returns a list of duck objects in the duck manager. Accepts either a string or list0 of strings containing id's. Otherwise if id is omitted it makes all duck data entries into a list of duck objects."""
        if id:
            if type(id) == list:
                # for item in id:
                self.ducklist = [Duck(duck)
                                 for duck in self.data if duck["_id"] in id]
                # for duck in self.data:
                #     if duck["_id"] == item:
                #         self.duck_list.append(Duck(duck))
            elif type(id) == str:
                for duck in self.data:
                    if duck["_id"] == id:
                        self.duck_list.append(Duck(duck))
            else:
                raise ValueError(
                    "Id must either be a string or list of strings")
        else:
            for duck in self.data:
                self.duck_list.append(Duck(duck))
        return self.duck_list


class Duck:
    def __init__(self, data: dict):
        # Main fields
        self.id = data["_id"]
        self.name = data["name"]
        self.assembler = data["assember"]
        self.adjectives = data["adjectives"]
        self.derpy = data["derpy"]
        self.bio = data["bio"]
        self.date = data["date"]
        self.approved = data["approved"]
        self.version = data["__v"]

        # Body fields
        self.head_color = data["body"]["head"]
        self.front1_color = data["body"]["front1"]
        self.front2_color = data["body"]["front2"]
        self.back1_color = data["body"]["back1"]
        self.back2_color = data["body"]["back2"]

        # Stats fields
        self.strength = data["stats"]["strength"]
        self.health = data["stats"]["health"]
        self.focus = data["stats"]["focus"]
        self.intelligence = data["stats"]["intelligence"]
        self.kindness = data["stats"]["kindness"]

    def __str__(self):
        return json.dumps(self)


if __name__ == "__main__":
    manager = DuckManager()
    print(manager.create_duck_list())
