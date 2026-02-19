import os
import pathlib
import sys
import argparse
parent = str(pathlib.Path(__file__).parent.parent) + "/"
sys.path.append(parent)

os.environ["PPPBOT_CDS_ONLY"] = "yes"

import env
import helpers


parser = argparse.ArgumentParser(prog='cdstester', description='cdstester', epilog='cdstester')
parser.add_argument("filename")
parser.add_argument("-r", "--remote-name")
parser.add_argument("-a", "--server-addr")
parser.add_argument("-p", "--server-port")
parser.add_argument("-n", "--server-hostname")
parser.add_argument("-c", "--cert-path")
parser.add_argument("-u", "--upload", action="store_true")
parser.add_argument("-d", "--download", action="store_true")
args = parser.parse_args()

env.CDS_SERVER_HOST = env.CDS_SERVER_HOST if args.server_addr == None else args.server_addr
env.CDS_SERVER_HOSTNAME = env.CDS_SERVER_HOSTNAME if args.server_hostname == None else args.server_hostname
env.CDS_SERVER_PORT = env.CDS_SERVER_PORT if args.server_port == None else int(args.server_port)
env.CDS_CERT_PATH = env.CDS_CERT_PATH if args.cert_path == None else args.cert_path

filename = args.filename
remote_name = os.path.basename(filename) if args.remote_name == None else args.remote_name
if args.upload:
	f = open(filename, "rb")
	value = f.read()
	r = helpers.storage_upload(remote_name, value)
	if (r != True):
		print("an error occured writing to the remote Q-CDS server")
		exit(-1)
	f.close()

if args.download:
	f = open(filename, "wb")
	value = helpers.storage_download(remote_name)
	if value == False:
		print("an error occured reading from the remote Q-CDS server")
		exit(-1)
	f.write(value)
	f.close()
