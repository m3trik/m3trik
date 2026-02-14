try:
    from uitk.widgets.marking_menu._marking_menu import MarkingMenu

    print("MarkingMenu imported successfully")
except Exception as e:
    print(f"Failed to import MarkingMenu: {e}")
    exit(1)

try:
    from uitk.switchboard import Switchboard

    print("Switchboard imported successfully")
except Exception as e:
    print(f"Failed to import Switchboard: {e}")
    exit(1)

print("Imports verified.")
