import os
import glob


def get_size(path):
    """
    Calculate total size of files inside a directory.
    Returns size in bytes.
    """
    total_size = 0

    if not os.path.exists(path):
        return 0

    try:
        for root, dirs, files in os.walk(path, topdown=True):

            # Avoid inaccessible directories
            accessible_dirs = []

            for directory in dirs:
                directory_path = os.path.join(root, directory)

                try:
                    if os.access(directory_path, os.R_OK):
                        accessible_dirs.append(directory)
                except OSError:
                    pass

            dirs[:] = accessible_dirs

            for file in files:
                file_path = os.path.join(root, file)

                try:
                    total_size += os.path.getsize(file_path)
                except (PermissionError, FileNotFoundError, OSError):
                    continue

    except (PermissionError, FileNotFoundError, OSError):
        pass

    return total_size


def bytes_to_mb(size):
    return size / (1024 * 1024)


def bytes_to_gb(size):
    return size / (1024 * 1024 * 1024)


def get_all_users():
    """
    Get all user directories under C:\\Users.
    """
    users_path = r"C:\Users"

    if not os.path.exists(users_path):
        return []

    users = []

    for user in os.listdir(users_path):

        user_path = os.path.join(users_path, user)

        if os.path.isdir(user_path):
            users.append(user_path)

    return users


def get_browser_cache_paths():

    cache_paths = []

    users = get_all_users()

    for user_path in users:

        # =========================
        # Chrome
        # =========================

        chrome_user_data = os.path.join(
            user_path,
            r"AppData\Local\Google\Chrome\User Data"
        )

        if os.path.exists(chrome_user_data):

            # Default, Profile 1, Profile 2, etc.
            profiles = glob.glob(
                os.path.join(
                    chrome_user_data,
                    "*"
                )
            )

            for profile in profiles:

                cache_path = os.path.join(
                    profile,
                    r"Cache\Cache_Data"
                )

                if os.path.isdir(cache_path):
                    cache_paths.append(
                        ("Chrome", user_path, profile, cache_path)
                    )

        # =========================
        # Edge
        # =========================

        edge_user_data = os.path.join(
            user_path,
            r"AppData\Local\Microsoft\Edge\User Data"
        )

        if os.path.exists(edge_user_data):

            # Default, Profile 1, Profile 2, etc.
            profiles = glob.glob(
                os.path.join(
                    edge_user_data,
                    "*"
                )
            )

            for profile in profiles:

                cache_path = os.path.join(
                    profile,
                    r"Cache\Cache_Data"
                )

                if os.path.isdir(cache_path):
                    cache_paths.append(
                        ("Edge", user_path, profile, cache_path)
                    )

    return cache_paths


def main():

    print("=" * 80)
    print("                    SYSTEM CACHE ANALYZER")
    print("=" * 80)

    total_cache = 0

    # ==========================================================
    # Windows User Temp
    # ==========================================================

    print("\nUSER TEMP FILES")
    print("-" * 80)

    users = get_all_users()

    for user_path in users:

        username = os.path.basename(user_path)

        temp_path = os.path.join(
            user_path,
            r"AppData\Local\Temp"
        )

        if os.path.exists(temp_path):

            size = get_size(temp_path)
            total_cache += size

            print(
                f"{username:<25} "
                f"{bytes_to_mb(size):>10.2f} MB"
            )

    # ==========================================================
    # Windows System Temp
    # ==========================================================

    print("\nWINDOWS TEMP")
    print("-" * 80)

    windows_temp = r"C:\Windows\Temp"

    size = get_size(windows_temp)
    total_cache += size

    print(
        f"C:\\Windows\\Temp       "
        f"{bytes_to_mb(size):>10.2f} MB"
    )

    # ==========================================================
    # System32 Temp
    # ==========================================================

    print("\nSYSTEM32 TEMP")
    print("-" * 80)

    system32_temp = r"C:\Windows\System32\temp"

    size = get_size(system32_temp)
    total_cache += size

    print(
        f"C:\\Windows\\System32\\temp "
        f"{bytes_to_mb(size):>10.2f} MB"
    )

    # ==========================================================
    # Windows Prefetch
    # ==========================================================

    print("\nWINDOWS PREFETCH")
    print("-" * 80)

    prefetch = r"C:\Windows\Prefetch"

    size = get_size(prefetch)
    total_cache += size

    print(
        f"C:\\Windows\\Prefetch  "
        f"{bytes_to_mb(size):>10.2f} MB"
    )

    # ==========================================================
    # Chrome & Edge
    # ==========================================================

    print("\nBROWSER CACHE")
    print("-" * 80)

    browser_paths = get_browser_cache_paths()

    chrome_total = 0
    edge_total = 0

    for browser, user_path, profile, cache_path in browser_paths:

        username = os.path.basename(user_path)
        profile_name = os.path.basename(profile)

        size = get_size(cache_path)

        total_cache += size

        if browser == "Chrome":
            chrome_total += size
        else:
            edge_total += size

        print(
            f"{browser:<10} "
            f"User: {username:<20} "
            f"Profile: {profile_name:<15} "
            f"{bytes_to_mb(size):>10.2f} MB"
        )

    # ==========================================================
    # Summary
    # ==========================================================

    print("\n" + "=" * 80)
    print("                         SUMMARY")
    print("=" * 80)

    print(
        f"Chrome Cache Total : "
        f"{bytes_to_mb(chrome_total):.2f} MB "
        f"({bytes_to_gb(chrome_total):.2f} GB)"
    )

    print(
        f"Edge Cache Total   : "
        f"{bytes_to_mb(edge_total):.2f} MB "
        f"({bytes_to_gb(edge_total):.2f} GB)"
    )

    print(
        f"TOTAL CACHE        : "
        f"{bytes_to_mb(total_cache):.2f} MB "
        f"({bytes_to_gb(total_cache):.2f} GB)"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()