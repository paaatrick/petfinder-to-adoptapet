import os
import re
import sys
from datetime import datetime
import requests
import xml.etree.ElementTree as etree


class PetFinder:
    def __init__(self, api_key):
        self._api_key = api_key

    def get_shelter_pets(self, shelter_id, status="A", translator=None):
        count = 200
        max_retries = 5
        params = dict(
            key=self._api_key,
            id=shelter_id,
            status=status,
            offset=0,
            count=count,
            output="full",
            format="xml"
        )
        while True:
            try_num = 0
            while try_num < max_retries:
                try_num += 1
                print("Petfinder offset = {0}; attempt = {1}".format(params["offset"], try_num))
                resp = requests.get("http://api.petfinder.com/shelter.getPets", params=params)
                if resp.status_code != 200:
                    return
                xml = etree.fromstring(resp.text)
                status = xml.find("header/status")
                if status.findtext("code") == '100':
                    break
            if try_num == max_retries:
                raise ConnectionError("Petfinder responded with: " + status.findtext("message"))

            next_offset = int(xml.find("lastOffset").text)
            pets = xml.findall(".//pet")
            if not pets:
                return
            for pet in pets:
                if callable(translator):
                    yield translator(pet)
                else:
                    yield pet
            if next_offset - params["offset"] < count:
                return
            params["offset"] = next_offset


class AnimalTranslator():
    def __init__(self, config):
        self.config = config

    def translate(self, xml):
        animal = xml.find("animal").text
        animal_class_name = re.sub("[^a-zA-Z]", "", animal.title())
        return getattr(sys.modules[__name__], animal_class_name, Animal)(xml, self.config)


class Animal():
    def __init__(self, xml, config):
        self._xml = xml
        self._config = config
        self._options = [o.text for o in self._xml.findall(".//option")]
        self._breeds = [o.text for o in self._xml.findall(".//breed")]

        text_fields = ("shelterPetId", "animal", "name", "age", "sex",
                       "description", "status")
        for attr in text_fields:
            setattr(self, attr, (self._xml.find(attr).text or "").strip())

        self.last_update = datetime.strptime(self._xml.find("lastUpdate").text,
                                             "%Y-%m-%dT%H:%M:%SZ")

        # description can have funky double-encoding problems sometimes. try to sniff
        # that out and repair it here
        funky_chars = ("\xe2\x80\x94", "\xe2\x80\x9c", "\xe2\x80\x93", "\xe2\x80\x99")
        if self.description and any(funk in self.description for funk in funky_chars):
            self.description = self.description.encode("raw_unicode_escape").decode("utf-8")

        options_map = (
            ("specialNeeds", "special_needs", "Y"),
            ("noDogs", "good_w_dogs", "N"),
            ("noCats", "good_w_cats", "N"),
            ("noKids", "good_w_kids", "N"),
            ("noClaws", "declawed", "Y"),
            ("hasShots", "shots_current", "Y"),
            ("housebroken", "housetrained", "Y"),
            ("housetrained", "housetrained", "Y"),
            ("altered", "spayed_neutered", "Y"),
        )
        for (option, attr, value) in options_map:
            if option in self._options:
                setattr(self, attr, value)

        mix = xml.find("mix")
        self.purebred = "Y" if mix and mix.text == "Y" else "N"

        self._process_breeds()
        self._process_size()

        self._photo_urls = dict()
        processed_ids = set()
        for photo in self._xml.findall(".//photo"):
            photo_id = photo.attrib["id"]
            if photo_id not in processed_ids:
                processed_ids.add(photo_id)
                (photo_url, _, _) = photo.text.partition("?")
                photo_filename = "{0}-{1}.jpg".format(self.shelterPetId.replace("/", "%2F"), photo_id)
                self._photo_urls[photo_filename] = photo_url

    def _process_breeds(self):
        self.breed = self._breeds[0]

    def _process_size(self):
        self.size = self._xml.find("size").text
        if self.size == "XL":
            self.size = "L"

    def to_dict(self):
        return {field: getattr(self, field, "") for field in self._config.get_columns()}

    def photo_files(self):
        return self._photo_urls.keys()

    def download_images(self, destination):
        for photo_filename, photo_url in self._photo_urls.items():
            response = requests.get(photo_url)
            with open(os.path.join(destination, photo_filename), "wb") as photo_file:
                photo_file.write(response.content)


class Cat(Animal):

    def __init__(self, xml, config):
        super(Cat, self).__init__(xml, config)

    def _process_breeds(self):
        breed_set = set(self._breeds)
        config_colors = self._config.get_shelter_values("color")
        config_breeds = self._config.get_shelter_values("breed")

        # 1 -- if all else fails, this seems reasonable
        self.breed = "Domestic Short Hair"
        self.color = ""

        # 2 -- check the breed-color options since they are probably least specific
        color_breeds = breed_set.intersection(config_colors, config_breeds)
        if color_breeds:
            color_breed = next(iter(color_breeds))
            self.breed = color_breed
            self.color = color_breed
            breed_set -= color_breeds

        # 3 -- check the color options
        colors = breed_set.intersection(config_colors)
        if colors:
            color = next(iter(colors))
            self.color = color
            breed_set -= colors

        # 4 -- anything left over should be a specific breed
        if breed_set:
            self.breed = next(iter(breed_set))


class Dog(Animal):

    def __init__(self, xml, config):
        super(Dog, self).__init__(xml, config)

    def _process_breeds(self):
        config_colors = self._config.get_shelter_values("color")
        config_breeds = self._config.get_shelter_values("breed")

        # if one of the breeds includes color information, set it as the color
        color_breeds = [breed for breed in self._breeds if breed in config_breeds and breed in config_colors]
        if color_breeds:
            self.color = next(iter(color_breeds))

        mapped_breeds = [breed for breed in self._breeds
                         if self._config.get_mapped_value("breed", breed) != "SKIP"]
        if len(mapped_breeds) == 0:
            self.breed = self._breeds[0]
        elif len(mapped_breeds) == 1:
            self.breed = mapped_breeds[0]
        else:
            self.breed = mapped_breeds[0]
            self.breed_2 = mapped_breeds[1]

    def _process_size(self):
        self.size = self._xml.find("size").text


class Rabbit(Animal):

    def __init__(self, xml, config):
        super(Rabbit, self).__init__(xml, config)

        if self.age == "Baby":
            self.age = "Young"


class SmallFurry(Animal):

    def __init__(self, xml, config):
        super(SmallFurry, self).__init__(xml, config)

        if self.breed == "Tarantula":
            self.animal = "Reptile"


class BarnYard(Animal):

    def __init__(self, xml, config):
        super(BarnYard, self).__init__(xml, config)


class Bird(Animal):

    def __init__(self, xml, config):
        super(Bird, self).__init__(xml, config)


class Horse(Animal):

    def __init__(self, xml, config):
        super(Horse, self).__init__(xml, config)

    def _process_breeds(self):
        self.breed = self._breeds[0]
        if len(self._breeds) > 1:
            self.breed_2 = self._breeds[1]


class Pig(Animal):

    def __init__(self, xml, config):
        super(Pig, self).__init__(xml, config)


class Reptile(Animal):

    def __init__(self, xml, config):
        super(Reptile, self).__init__(xml, config)
