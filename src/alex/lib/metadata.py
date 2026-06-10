from importlib.metadata import version

PACKAGE_NAME = "alex"


def package_version(package_name: str = PACKAGE_NAME) -> str:
    return version(package_name)
