import asyncio
import glob
import logging
import os
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import ujson
from jobs import (
    holo_heartbeat,
    hololive_main,
    niji_heartbeat,
    nijisanji_main,
    others_main,
    update_channels_stats,
    youtube_live_heartbeat,
    youtube_video_feeds,
)
from jobs.utils import Jetri, VTBiliDatabase

BASE_FOLDER_PATH = "./"  # Modify this
MONGODB_URI = "mongodb://127.0.0.1:12345"  # Modify this
MONGODB_DBNAME = "vtbili"  # Modify this
YT_API_KEY = ""  # Modify this

INTERVAL_BILI_CHANNELS = 6 * 60  # In minutes
INTERVAL_BILI_UPCOMING = 4  # In minutes
INTERVAL_BILI_LIVE = 2  # In minutes
INTERVAL_YT_FEED = 2  # In minutes
INTERVAL_YT_LIVE = 1  # In minutes

if __name__ == "__main__":
    logfiles = os.path.join(BASE_FOLDER_PATH, "vtbili_server.log")
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[logging.FileHandler(logfiles, "a", "utf-8")],
        format="[%(asctime)s] - (%(name)s)[%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    vtlog = logging.getLogger("vtbili_server")
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)

    formatter1 = logging.Formatter("[%(levelname)s] (%(name)s): %(message)s")
    console.setFormatter(formatter1)
    vtlog.addHandler(console)

    vtlog.info("Opening new loop!")
    loop_de_loop = asyncio.get_event_loop()
    jetri_co = Jetri(loop_de_loop)
    vtlog.info(
        f"Connecting to database using: {MONGODB_URI} ({MONGODB_DBNAME})"
    )
    vtbili_db = VTBiliDatabase(MONGODB_URI, MONGODB_DBNAME)
    vtlog.info("Connected!")

    vtlog.info("Initiating scheduler...")
    scheduler = AsyncIOScheduler()

    vtlog.info(
        f"With Interval:\n\t- BiliBili Live/Upcoming/Channels: "
        f"{INTERVAL_BILI_LIVE}/{INTERVAL_BILI_UPCOMING}"
        f"/{INTERVAL_BILI_CHANNELS} mins\n\t"
        f"- YouTube Feed/Live: {INTERVAL_YT_FEED}/{INTERVAL_YT_LIVE} mins"
    )

    vtlog.info("Adding jobs...")
    scheduler.add_job(
        hololive_main,
        "interval",
        kwargs={"DatabaseConn": vtbili_db},
        minutes=INTERVAL_BILI_UPCOMING,
    )
    scheduler.add_job(
        nijisanji_main,
        "interval",
        kwargs={"DatabaseConn": vtbili_db},
        minutes=INTERVAL_BILI_UPCOMING,
    )

    others_dataset = os.path.join(
        BASE_FOLDER_PATH, "dataset", "_bilidata_other.json"
    )

    scheduler.add_job(
        others_main,
        "interval",
        kwargs={"DatabaseConn": vtbili_db, "dataset_path": others_dataset},
        minutes=INTERVAL_BILI_UPCOMING,
    )

    dataset_all = glob.glob(
        os.path.join(BASE_FOLDER_PATH, "dataset", "_bili*.json")
    )

    scheduler.add_job(
        update_channels_stats,
        "interval",
        kwargs={"DatabaseConn": vtbili_db, "dataset_set": dataset_all},
        minutes=INTERVAL_BILI_CHANNELS,
    )

    others_yt_dataset = os.path.join(
        BASE_FOLDER_PATH, "dataset", "_ytdata_other.json"
    )

    scheduler.add_job(
        youtube_video_feeds,
        "interval",
        kwargs={
            "DatabaseConn": vtbili_db,
            "dataset": others_yt_dataset,
            "yt_api_key": YT_API_KEY,
        },
        minutes=INTERVAL_YT_FEED,
    )

    scheduler.add_job(
        youtube_live_heartbeat,
        "interval",
        kwargs={"DatabaseConn": vtbili_db, "yt_api_key": YT_API_KEY},
        minutes=INTERVAL_YT_LIVE,
    )

    ytbili_file = os.path.join(
        BASE_FOLDER_PATH, "dataset", "_ytbili_mapping.json"
    )
    with open(ytbili_file, "r", encoding="utf-8") as fp:
        ytbili_mapping = ujson.load(fp)

    scheduler.add_job(
        holo_heartbeat,
        "interval",
        kwargs={
            "DatabaseConn": vtbili_db,
            "JetriConn": jetri_co,
            "room_dataset": ytbili_mapping,
        },
        minutes=INTERVAL_BILI_LIVE,
    )

    scheduler.add_job(
        niji_heartbeat,
        "interval",
        kwargs={
            "DatabaseConn": vtbili_db,
            "JetriConn": jetri_co,
            "room_dataset": ytbili_mapping,
        },
        minutes=INTERVAL_BILI_LIVE,
    )

    vtlog.info("Doing first run!")
    jobs_data = [
        asyncio.ensure_future(hololive_main(vtbili_db)),
        asyncio.ensure_future(nijisanji_main(vtbili_db)),
        asyncio.ensure_future(others_main(vtbili_db, others_dataset)),
        asyncio.ensure_future(update_channels_stats(vtbili_db, dataset_all)),
        asyncio.ensure_future(youtube_live_heartbeat(vtbili_db, YT_API_KEY)),
        asyncio.ensure_future(
            youtube_video_feeds(
                vtbili_db, others_yt_dataset, YT_API_KEY
            )
        ),
        asyncio.ensure_future(
            holo_heartbeat(vtbili_db, jetri_co, ytbili_mapping)
        ),
        asyncio.ensure_future(
            niji_heartbeat(vtbili_db, jetri_co, ytbili_mapping)
        ),
    ]
    loop_de_loop.run_until_complete(asyncio.gather(*jobs_data))
    vtlog.info("Starting scheduler!")
    scheduler.start()

    try:
        loop_de_loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        vtlog.info("CTRL+C Called, stopping everything...")
        loop_de_loop.run_until_complete(jetri_co.close())
        loop_de_loop.stop()
        loop_de_loop.close()

    vtlog.info("Scheduler stopped.")
