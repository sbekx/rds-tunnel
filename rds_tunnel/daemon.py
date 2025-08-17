import os
import sys

def daemonize():
	"""Double-fork magic to daemonize a process."""
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0)
	except OSError as e:
		sys.stderr.write(f"fork #1 failed: {e.errno} ({e.strerror})\\n")
		sys.exit(1)

	os.setsid()

	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0)
	except OSError as e:
		sys.stderr.write(f"fork #2 failed: {e.errno} ({e.strerror})\\n")
		sys.exit(1)