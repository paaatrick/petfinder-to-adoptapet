#!/usr/bin/env python

import configparser
import csv
import datetime
import ftplib
import glob
import os

import adoptapet
import petfinder


if __name__ == "__main__":

    def fix_id(the_pet):
        if not the_pet.shelterPetId:
            the_pet.shelterPetId = the_pet.name
        elif the_pet.shelterPetId in processed_ids:
            the_pet.shelterPetId = the_pet.shelterPetId + "-" + the_pet.name
        the_pet.shelterPetId = the_pet.shelterPetId[:50]

    settings = configparser.ConfigParser()
    settings.read("settings.ini")

    this_dir = os.path.dirname(os.path.realpath(__file__))
    upload_dir = os.path.join(this_dir, "upload")
    photos_dir = os.path.join(upload_dir, "photos")
    if not os.path.exists(photos_dir):
        os.makedirs(photos_dir)

    config = adoptapet.ImportConfigParser()
    config.read(os.path.join(upload_dir, "import.cfg"))

    translator = petfinder.AnimalTranslator(config)

    pf = petfinder.PetFinder(settings.get("PetFinder", "api_key"))
    pets_file_name = os.path.join(upload_dir, "pets.csv")
    processed_ids = set()
    photos_to_upload = []
    with ftplib.FTP("autoupload.adoptapet.com") as ftp:
        ftp.login(settings.get("AdoptAPet", "ftp_user"),
                  settings.get("AdoptAPet", "ftp_pass"))
        uploaded_photos = [item[0] for item in ftp.mlsd("photos")]
        downloaded_photos = [os.path.basename(p) for p in glob.glob(os.path.join(photos_dir, "*.jpg"))]
        with open(pets_file_name, "w", newline="", encoding="ascii", errors="xmlcharrefreplace") as pets_file:
            writer = csv.DictWriter(pets_file, config.get_columns())
            writer.writeheader()
            for pet in pf.get_shelter_pets(settings.get("PetFinder", "shelter_id"), translator=translator.translate):
                fix_id(pet)
                writer.writerow(pet.to_dict())
                photos_to_upload.extend(pet.photo_files())
                processed_ids.add(pet.shelterPetId)
                test_file = "{0}-1.jpg".format(pet.shelterPetId)
                if test_file not in downloaded_photos:
                    pet.download_images(photos_dir)

            cutoff_date = datetime.datetime.today() - datetime.timedelta(days=6 * 30)
            for pet in pf.get_shelter_pets(settings.get("PetFinder", "shelter_id"), status="X", translator=translator.translate):
                if pet.last_update < cutoff_date:
                    continue
                fix_id(pet)
                writer.writerow(pet.to_dict())
                photos_to_upload.extend(pet.photo_files())
                processed_ids.add(pet.shelterPetId)
                test_file = "{0}-1.jpg".format(pet.shelterPetId)
                if test_file not in downloaded_photos:
                    pet.download_images(photos_dir)

        for file_name in ("pets.csv", "import.cfg"):
            with open(os.path.join(upload_dir, file_name), "rb") as file:
                name = os.path.basename(file.name)
                print(name)
                ftp.storbinary("STOR " + name, file)

        if "photos" not in [item[0] for item in ftp.mlsd()]:
            ftp.mkd("photos")
        ftp.cwd("photos")

        for file_name in photos_to_upload:
            if file_name in uploaded_photos:
                continue
            print(file_name)
            try:
                with open(os.path.join(photos_dir, file_name), "rb") as file:
                    ftp.storbinary("STOR " + file_name, file)
            except FileNotFoundError:
                print("couldn't find file!")
