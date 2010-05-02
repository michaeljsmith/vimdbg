import vim

class Error(Exception): pass

class CreateBufferError(Error):
	def __init__(self, msg): self.msg = msg

class BufferMissingError(Error):
	def __init__(self, msg): self.msg = msg

session_id = 100
def get_session_id():
	global session_id
	new_session_id = session_id
	session_id += 1
	return new_session_id

class GdbSession(object):
	def __init__(self):
		self.session_id = get_session_id()
		self.log_window = LogWindow(self.session_id)
		self.log_window.create_buffer()
		self.log_window.display()
		self.log_window.log_message("This is the log window.")

class GdbDriver(object):
	pass

class BreakpointCollection(object):
	pass

class BreakpointWindow(object):
	pass

class WatchList(object):
	pass

class WatchWindow(object):
	pass

class LogWindow(object):

	def __init__(self, session_id):
		self.buffer = None
		self.session_id = session_id

	def create_buffer(self):
		buf_name = "/DbgLog" + str(self.session_id)
		cmd = "bad " + buf_name
		vim.command(cmd)
		print [b.name for b in vim.buffers]
		bufs = [b for b in vim.buffers if b.name == buf_name]
		try:
			self.buffer = bufs[0]
		except IndexError:
			raise CreateBufferError("Error while creating log buffer.")

	def display(self):
		if not self.buffer:
			raise BufferMissingError("Cannot display log window - buffer not created.")
		cmd = "sb " + self.buffer.name
		vim.command(cmd)

	def log_message(self, msg):
		if not self.buffer:
			raise BufferMissingError("Cannot display log message - buffer not created.")
		self.buffer.append(msg)

