import vim
import subprocess
import threading
import time
import re

def log(msg):
	f = open('log.txt', 'a+')
	try:
		f.write(msg)
	finally:
		f.close()

class Error(Exception): pass

class CreateBufferError(Error):
	def __init__(self, msg): self.msg = msg

class BufferMissingError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerAlreadyRunningError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerMissingError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerSpawnError(Error):
	def __init__(self, msg): self.msg = msg

class QueueEmptyError(Error):
	def __init__(self, msg): self.msg = msg

class QueueCorruptError(Error):
	def __init__(self, msg): self.msg = msg

class ThreadNotRunningError(Error):
	def __init__(self, msg): self.msg = msg

class ThreadAlreadyRunningError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerStdoutClosed(Error):
	def __init__(self, msg): self.msg = msg

class DriverBreakpointsAlreadyConnectedError(Error):
	def __init__(self, msg): self.msg = msg

class DriverBreakpointsNotConnectedError(Error):
	def __init__(self, msg): self.msg = msg

class DriverAlreadyRunningError(Error):
	def __init__(self, msg): self.msg = msg

class BreakpointMissingError(Error):
	def __init__(self, msg): self.msg = msg

class BreakpointAlreadyExistsError(Error):
	def __init__(self, msg): self.msg = msg

class UnexpectedResponseError(Error):
	def __init__(self, msg): self.msg = msg

class ResponseTimeoutError(Error):
	def __init__(self, msg): self.msg = msg

class GdbError(Error):
	def __init__(self, msg): self.msg = msg

class Delegate(object):
	def __init__(self):
		self.hndlrs = {}

	def add_handler(self, id, hndlr):
		self.hndlrs[id] = hndlr

	def remove_handler(self, id):
		del self.hndlrs[id]

	def signal(self, *args):
		for hndlr in self.hndlrs.itervalues():
			hndlr(*args)

class ThreadMessageQueue(object):
	def __init__(self):
		self.items = []
		self.lock = threading.Lock()

	def append(self, message):
		self.lock.acquire()
		try:
			self.items.append(message)
		finally:
			self.lock.release()

	def pop(self):
		self.lock.acquire()
		message = None
		try:
			message = self.items.pop(0)
		finally:
			self.lock.release()
		return message

	def empty(self):
		self.lock.acquire()
		try:
			l = len(self.items)
		finally:
			self.lock.release()
		return l == 0

def deserialize_gdb_record(rcrd, text):

	def extract_pattern(ptn, tx):
		m = re.match(ptn, tx)
		val = m.group(1)
		end = m.end(1)
		return val, tx[end:]

	tx = text
	rcrd.response, tx = extract_pattern(r"([A-Za-z0-9_]+)[ \t\r\n]*", tx)
	log('rcrd.response = ' + str(rcrd.response) + '\n')
	try:
		while True:
			comma, tx = extract_pattern(r"(,)[ \t]*", tx)
			log('comma = ' + str(comma) + '\n')
			key, tx = extract_pattern(r"([A-Za-z0-9_]+)[ \t\r\n]*", tx)
			log('key = ' + key + '\n')
			equals, tx = extract_pattern(r"(=)[ \t\r\n]*", tx)
			log('equals = ' + equals + '\n')
			value, tx = extract_pattern(r'"((?:[^"\\]*\\")*[^"\\]*)"', tx)
			log('value = ' + value + '\n')
			setattr(rcrd, key, value)
	except IndexError:
		pass
	except AttributeError:
		pass
	log(str(rcrd.__dict__) + '\n')

session_id = 100
def get_session_id():
	global session_id
	new_session_id = session_id
	session_id += 1
	return new_session_id

class Session(object):
	def __init__(self, driver, bps):
		self.session_id = get_session_id()
		self.driver = driver
		self.driver_proxy = DriverProxy(driver)
		self.driver.hdlr = self.driver_proxy
		self.log_window = LogWindow(self.session_id)
		self.bps = bps
		self.driver_connected_to_bps = False

		self.log_window.create_buffer()

		# Display all communications in the log window.
		self.driver_proxy.on_communication.add_handler(
				self.log_window, self.log_window.log_message)
		self.driver.on_log.add_handler(
				self.log_window, self.log_window.log_message)

		# Log all breakpoint operations.
		def log_breakpoint_add(id, file, line):
			self.log_window.log_message(
					"Breakpoint added(" + str(id) + "): " +
					file + "(" + str(line) + ")")
		def log_breakpoint_remove(id, file, line):
			self.log_window.log_message(
					"Breakpoint removed(" + str(id) + "): " +
					file + "(" + str(line) + ")")
		self.bps.on_add.add_handler(self.log_window, log_breakpoint_add)
		self.bps.on_remove.add_handler(self.log_window, log_breakpoint_remove)

	def display_log_window(self):
		self.log_window.display()

	def start_debugger(self):
		self.log_window.log_message("Starting debugger.\n")

		self.driver_proxy.start()

	def stop_debugger(self):
		self.log_window.log_message("Stopping debugger.")
		if self.driver_connected_to_bps:
			self.disconnect_driver_from_breakpoints()
		self.driver_proxy.stop()

	def run_debugger(self):
		if not self.driver_connected_to_bps:
			self.connect_driver_to_breakpoints()
		self.log_window.log_message("Running debugger.\n")
		self.driver_proxy.run()

	def shutdown(self):
		try:
			self.stop_debugger()
		except DebuggerMissingError: pass

	def update(self):
		self.driver_proxy.update()

	def connect_driver_to_breakpoints(self):
		if self.driver_connected_to_bps:
			raise DriverBreakpointsAlreadyConnectedError(
					"Cannot connect driver to breakpoints - already connected.")
		self.log_window.log_message('Connecting breakpoings.' + str(self.bps.bps))
		self.bps.on_add.add_handler(self.driver_proxy, self.driver_proxy.add_breakpoint)
		self.bps.on_remove.add_handler(self.driver_proxy, self.driver_proxy.remove_breakpoint)
		for id, (file, line) in self.bps.bps.iteritems():
			self.driver_proxy.add_breakpoint(id, file, line)
		self.driver_connected_to_bps = True

	def disconnect_driver_from_breakpoints(self):
		if not self.driver_connected_to_bps:
			raise DriverBreakpointsNotConnectedError(
					"Cannot disconnect driver from breakpoints - not connected.")
		self.bps.on_add.remove_handler(self.driver_proxy)
		self.bps.on_remove.remove_handler(self.driver_proxy)
		#for id, (drvr_id, file, line) in self.driver_proxy.bps.iteritems():
		#	self.driver_proxy.remove_breakpoint(id)
		self.driver_connected_to_bps = False

class DriverProxy(object):
	def __init__(self, driver):
		self.driver = driver
		self.on_communication = Delegate()
	
	def handle_communication(self, msg):
		self.on_communication.signal(msg)

	def start(self):
		self.driver.start()

	def stop(self):
		self.driver.stop()

	def update(self):
		self.driver.read_all_pending()

	def run(self):
		self.driver.run()

	def add_breakpoint(self, id, file, line):
		self.driver.add_breakpoint(id, file, line)

	def remove_breakpoint(self, id):
		self.driver.remove_breakpoint(id)

class GdbDriver(object):
	def __init__(self):
		self.process = None
		self.running = False
		self.on_log = Delegate()
		self.message_queue = ThreadMessageQueue()
		self.response_handler_queue = []
		self.thread = None
		self.hdlr = None

	def start(self):
		if self.process:
			raise DebuggerAlreadyRunningError(
					"Cannot start debugger: GDB is already running.")
		try:
			self.process = subprocess.Popen("gdb --interpreter mi", shell=True, bufsize=0,
					stdin=subprocess.PIPE, stdout=subprocess.PIPE,
					stderr=subprocess.PIPE)
		except OSError, e:
			raise DebuggerSpawnError("Failed to start GDB: " + e.strerror)

		if self.thread:
			raise ThreadAlreadyRunningError(
					'Cannot start listen thread - already running.')
		listen = self.listen
		class Thread(threading.Thread):
			def run(self):
				listen()
		self.thread = Thread()
		self.thread.setDaemon(True)
		self.thread.start()

		try:
			self.read_until_challenge()
		except ResponseTimeoutError:
			raise ResponseTimeoutError('Timeout after starting debugger.')

	def stop(self):
		if not self.process:
			raise DebuggerMissingError("Cannot stop debugger: GDB not running.")
		if not self.thread:
			raise ThreadNotRunningError(
					'Cannot stop debugger - listen thread not running.')
		self.process.stdin.close()
		self.thread.join()
		self.thread = None
		self.read_all_pending()

	def run(self):
		if not self.process:
			raise DebuggerMissingError("Cannot run debugger: GDB not running.")
		if self.running:
			raise DriverAlreadyRunningError("Cannot start debugging: already debugging.")
		exc = [None]
		def on_response(rcrd):
			if rcrd.response == 'error':
				self.on_log.signal('Error when running gdb.')
				exc[0] = GdbError('Gdb responded: ' + rcrd.msg)
			elif rcrd.response != 'running':
				exc[0] = UnexpectedResponseError(
						'Unexpected response to -exec-run: ' + rcrd.response)
		self.response_handler_queue.append(on_response)
		self.process.stdin.write('-exec-run\n')
		try:
			self.read_until_challenge()
		except ResponseTimeoutError:
			raise ResponseTimeoutError('Timeout after running target.')
		if exc[0]:
			raise exc[0]

	def read(self):
		try:
			msg = self.message_queue.pop()
		except IndexError:
			raise QueueEmptyError('Tried to read from empty thread queue.')
		meth, args = msg
		try:
			f = getattr(self, meth)
		except AttributeError:
			raise QueueCorruptError('Unknown method "' + meth + '".')
		try:
			f(*args)
		except TypeError, e:
			raise QueueCorruptError('Invalid args in queue: "' +
					str(e) + '" (method="' + meth + '").')
	
	def handle_communication(self, ln):
		self.hdlr.handle_communication(ln)

	def handle_eof(self):
		print "Debugger process exitted."

	def handle_response(self, rcrd):
		rspns_hdlr = self.response_handler_queue.pop()
		rspns_hdlr(rcrd)

	def read_all_pending(self):
		while not self.message_queue.empty():
			self.read()

	def handle_challenge(self):
		self.on_log.signal('Base handle_challenge.')

	def read_until_challenge(self):
		self.on_log.signal('Read until challenge.')
		challenge_recv = [False]
		def on_challenge():
			self.on_log.signal('Challenge received.')
			challenge_recv[0] = True
		self.handle_challenge = on_challenge
		loop_cnt = 0
		while not challenge_recv[0]:
			loop_cnt += 1
			if loop_cnt > 20:
				raise ResponseTimeoutError('Response timeout.')
			while not self.message_queue.empty():
				self.read()
			if not challenge_recv[0]:
				time.sleep(0.1)
		del self.handle_challenge

	def set_file(self, file):
		self.on_log.signal("Setting debug file: " + file + "\n")
		if not self.process:
			raise DebuggerMissingError("Cannot set file: GDB not running.")
		if self.running:
			raise DriverAlreadyRunningError("Cannot set file: GDB already running.")
		def on_response(rcrd):
			if rcrd.response == 'error':
				raise GdbError('Gdb responded: ' + rcrd.msg)
			elif rcrd.response != 'done':
				raise UnexpectedResponseError(
						'Unexpected response to -file-exec-and-symbols: '
						+ rcrd.response)
		self.response_handler_queue.append(on_response)
		self.process.stdin.write('-file-exec-and-symbols ' + file + '\n')
		try:
			self.read_until_challenge()
		except ResponseTimeoutError:
			raise ResponseTimeoutError('Timeout after setting debug target.')

	def listen(self):
		log('listen start\n')
		while True:
			log('listen readline\n')
			ln = self.process.stdout.readline()
			if not ln:
				log('listen eof\n')
				self.message_queue.append(('handle_eof', []))
				break
			self.message_queue.append(('handle_communication', [ln.strip()]))
			if ln.find('(gdb)') >= 0:
				log('listen challenge\n')
				self.message_queue.append(('handle_challenge', ()))
			elif ln[0] == '^':
				log('listen response: ' + ln + '\n')
				class Record(object): pass
				rcrd = Record()
				deserialize_gdb_record(rcrd, ln[1:].strip('\r'))
				self.message_queue.append(('handle_response', [rcrd]))
			log('listen loop\n')
		log('listen end\n')
		self.process = None

	def add_breakpoint(self):
		self.on_log.signal("Adding breakpoint: " + file + ":" + str(line) + "\n")
		def on_response(rcrd):
			if rcrd.response != 'done':
				raise UnexpectedResponseError(
						'Unexpected response to -break-insert: '
						+ rcrd.response)
		self.response_handler_queue.append(on_response)
		cmd = '-break-insert ' + file + ':' + str(line) + '\n'
		self.process.stdin.write(cmd)
		self.read_until_challenge()

	def remove_breakpoint(self):
		asdf = self.doesntexist

class BreakpointCollection(object):
	def __init__(self):
		self.bps = {}
		self.on_add = Delegate()
		self.on_remove = Delegate()

	def add(self, id, file, line):
		if id in self.bps:
			raise BreakpointAlreadyExistsError(
					"Cannot add breakpoint " + id + " - id already in use.")
		self.bps[id] = (file, line)
		self.on_add.signal(id, file, line)

	def remove(self, id):
		try:
			file, line = self.bps[i]
			del self.bps[i]
		except KeyError:
			raise BreakpointMissingError(
					"Cannot remove breakpoint " + id + " - no such breakpoint.")
		self.on_remove.signal(id, file, line)

class LogWindow(object):
	def __init__(self, session_id):
		self.buffer = None
		self.session_id = session_id

	def create_buffer(self):
		buf_name = "DbgLog" + str(self.session_id)
		vim.command("bad " + buf_name)
		vim.command('call setbufvar("' + buf_name + '", "&buftype", "nofile")')
		vim.command('call setbufvar("' + buf_name + '", "&bufhidden", "hide")')
		vim.command('call setbufvar("' + buf_name + '", "&swapfile", 0)')
		bufs = [b for b in vim.buffers if b.name and b.name.find(buf_name) != -1]
		try:
			self.buffer = bufs[0]
		except IndexError:
			raise CreateBufferError("Error while creating log buffer.")

	def display(self):
		if not self.buffer:
			raise BufferMissingError("Cannot display log window - buffer not created.")
		existing_winds = [w for w in vim.windows if w.buffer == self.buffer]
		if not existing_winds:
			cmd = "sb " + self.buffer.name
			vim.command(cmd)

	def log_message(self, msg):
		if not self.buffer:
			raise BufferMissingError("Cannot display log message - buffer not created.")
		self.buffer.append(msg)
		for w in (w for w in vim.windows if w.buffer == self.buffer):
			w.cursor = len(self.buffer), 1
