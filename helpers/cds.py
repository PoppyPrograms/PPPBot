import hashlib
import env
import os
import socket
import ssl

def __generate_hash(message: str) -> bytes:
	return hashlib.md5(message.encode("utf-8")).digest()

def __generate_packet_header(type: int, message: bytes, direction: int) -> bytes:
	l = len(message)
	return env.CDS_TOKEN + bytes([type, l & 0xff, (l >> 8) & 0xff, direction]) + message

def __cds_recv_all(packet: bytes, sock):
	while True:
		try:
			p = sock.recv(4096, socket.MSG_DONTWAIT)
			if p == b"":
				break
			packet = packet + p
		except:
			return packet # done
	return packet

def __send_to_cds_server(packet: bytes) -> bytes:
	try:
		ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
		ssl_context.load_verify_locations(env.CDS_CERT_PATH)
		raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
		sock = ssl_context.wrap_socket(raw_sock, server_hostname=env.CDS_SERVER_HOSTNAME)
		sock.connect((env.CDS_SERVER_HOST, env.CDS_SERVER_PORT))
		sock.settimeout(1)
		sock.sendall(packet)
		r = sock.recv(4096)
		r = __cds_recv_all(r, sock)
		sock.shutdown(socket.SHUT_RDWR)
		sock.close()
		return r
	except Exception as e:
		return bytes([0xfe, 0x04, 0x00, 0x00]) + b"ERR\x00" # whatever

def storage_upload(filename: str, content: bytes) -> bool:
	hash = __generate_hash(os.path.basename(filename))
	packet = __generate_packet_header(0x00, hash, 0x01) + content
	response = __send_to_cds_server(packet)
	if len(response) < 4:
		return False
	if response[0] != 0xff:
		return False
	return True

def storage_download(filename: str) -> bytes | bool:
	hash = __generate_hash(os.path.basename(filename))
	packet = __generate_packet_header(0x00, hash, 0x00)
	response = __send_to_cds_server(packet)
	if len(response) < 4:
		return False
	if response[0] != 0xff:
		return False
	if response[3] != 0x01:
		return False
	return response[4:]
