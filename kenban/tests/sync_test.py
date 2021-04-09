from kenban.sync import get_all_images, get_all_templates, get_schedule, get_all_events
import logging
logging.getLogger().setLevel(logging.DEBUG)

get_all_images()
get_all_templates(True)
get_schedule()
get_all_events()
