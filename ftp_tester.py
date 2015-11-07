import configparser
import ftplib

settings = configparser.ConfigParser()
settings.read("settings.ini")

with ftplib.FTP("autoupload.adoptapet.com") as ftp:
    ftp.login(settings.get("AdoptAPet", "ftp_user"),
              settings.get("AdoptAPet", "ftp_pass"))
    print(ftp.getwelcome())
    ftp.delete("farts.foo")