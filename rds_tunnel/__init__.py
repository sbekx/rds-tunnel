("""Package initializer.

Suppress noisy deprecation warnings from paramiko/cryptography as early as
possible so those messages do not appear when importing the package.
""")
try:
	import warnings
	warnings.filterwarnings(
		"ignore",
		category=DeprecationWarning,
		module="paramiko"
	)
	try:
		from cryptography.utils import CryptographyDeprecationWarning
		warnings.filterwarnings(
			"ignore",
			category=CryptographyDeprecationWarning,
			module="paramiko"
		)
	except Exception:
		# cryptography may not be available at import time; ignore if so
		pass
except Exception:
	# Best-effort suppression; do not fail import if warnings/cryptography missing
	pass

