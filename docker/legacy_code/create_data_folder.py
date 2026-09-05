"""Create sequential legacy session folders."""

import os
import time

def create_data_folder() -> None:
    """Create the next numbered folder for today's date."""

    current_time = time.localtime()
    date_str = time.strftime("%Y_%m_%d", current_time)

    if not os.path.exists(date_str):
        os.makedirs(date_str)
        if not os.path.exists(date_str):
            print(f"The folder '{date_str}' could not be created.")
        else:
            print(f"The folder '{date_str}' has been created.")

    data_path = os.path.join(os.getcwd(), date_str)

    folders = next(os.walk(data_path))[1]

    numeric_folders = sorted([f for f in folders if len(f) >= 3 and f[:3].isdigit()], key=lambda x: int(x[:3]))

    if numeric_folders:
        latest_number = int(numeric_folders[-1][:3])
        new_data_fp = f"{latest_number + 1:03}"
    else:

        new_data_fp = "000"

    new_data_folder = os.path.join(data_path, new_data_fp)

    if not os.path.exists(new_data_folder):
        os.makedirs(new_data_folder)
        if not os.path.exists(new_data_folder):
            print(f"The folder '{new_data_folder}' could not be created.")
        else:
            print(f"The folder '{new_data_folder}' has been created.")
