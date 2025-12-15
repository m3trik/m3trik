import typing
import mayatk

diag = mayatk.Diagnostics

print(f"diag: {diag}")
print(f"typing.Any: {typing.Any}")
print(f"diag is typing.Any: {diag is typing.Any}")
print(f"diag == typing.Any: {diag == typing.Any}")
print(f"str(diag): {str(diag)}")
