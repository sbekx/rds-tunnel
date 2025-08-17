from datetime import datetime
import time
import os

def collector(log_file_path):
	# Clean up old log entries (older than 2 hours)
	# This is a simple cleanup for demonstration. For production, consider log rotation tools.
	log_file = open(os.path.expanduser(log_file_path), 'a+')
	log_file.seek(0)
	lines = log_file.readlines()
	log_file.truncate(0) # Clear the file
	log_file.seek(0)

	two_hours_ago = time.time() - (2 * 3600) # 2 hours in seconds
	
	for line in lines:
		try:
			# Attempt to parse timestamp from the beginning of the line
			timestamp_str = line.split(' - ')[0]
			# Assuming timestamp format 'YYYY-MM-DD HH:MM:SS,ms'
			dt_object = datetime.strptime(timestamp_str.split(',')[0], '%Y-%m-%d %H:%M:%S')
			line_timestamp = dt_object.timestamp()
			if line_timestamp >= two_hours_ago:
				log_file.write(line)
		except (ValueError, IndexError):
			# If parsing fails (e.g., line without timestamp or malformed),
			# write the line back. This handles lines without timestamps.
			log_file.write(line)
	log_file.flush()
	# End garbage collection

def clean(log_file_path):
	with open(os.path.expanduser(log_file_path), 'w') as f:
		f.truncate(0)
