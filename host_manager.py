import docker
from fabric import Connection
import logging
import os
import queue
import sys
import threading

# TODO: Implement checks on received host
# TODO: Fill container_volumes without hard-coding it

class HostManager:

        running_in_container = "RUNNING_IN_CONTAINER" in os.environ

        container_volumes = {
                "/home/ubuntu": "/root"
        }

        host_conf = {
                "ssh_username": "ubuntu",
                "docker_remote_api_port": 2375
        }

        def __init__(self):
                self._hosts = []
                self._reserved_hosts = []
                self._hosts_lock = threading.Lock()
                self._hosts_connections = {}
                self.logger = logging.getLogger("HostManager")
        
        def add_host(self, host):
                with self._hosts_lock:
                        self._hosts.append(host)
                self.logger.info("Added host {0}".format(host))

        def add_hosts_from_file(self, hosts_file_path):
                with open(hosts_file_path) as hosts_file:
                        hosts = []
                        for line in hosts_file:
                                stripped = line.strip()
                                hosts.append(stripped)
                with self._hosts_lock:
                        self._hosts.extend(hosts)

        def get_hosts(self):
                with self._hosts_lock:
                        return self._hosts.copy()
        
        def reserve_hosts(self, n_hosts):
                with self._hosts_lock:
                        if len(self._hosts) < n_hosts:
                                return False
                        for _ in range(n_hosts):
                                self._reserved_hosts.append(self._hosts.pop())
                                self.logger.debug("Reserved host {0}".format(self._reserved_hosts[-1]))
                        return self._reserved_hosts.copy()

        
        def free_hosts(self, hosts):
                with self._hosts_lock:
                        for host in hosts:
                                try:
                                        self._reserved_hosts.remove(host)
                                        self._hosts.append(host)
                                except ValueError:
                                        self.logger.error("Can't free host {0}. It wasn't previously reserved".format(host))

        @staticmethod
        def get_hosts_connections(hosts):
                hosts_connections = {}
                for host in hosts:
                        hosts_connections[host] = {
                                "docker": {
                                        "client": docker.DockerClient(base_url='tcp://%s:%d' % (host, HostManager.host_conf["docker_remote_api_port"])),
                                        "containers": {},
                                        "networks": {}
                                },
                                "ssh": Connection(host=host, user=HostManager.host_conf["ssh_username"])
                        }
                return hosts_connections

        @staticmethod
        def get_local_connections(check=True):
                local_connections = {}
                if "SERVER_IP" in os.environ:
                        local_connections["ip"] = os.environ["SERVER_IP"]
                else:
                        logging.getLogger("HostManager").warning("env SERVER_IP may be required but it is not set")
                local_docker = docker.from_env()
                local_connections["docker"] = {"client": local_docker, "containers": {}, "networks": {}}
                if check:
                        try:
                                local_docker.ping()
                        except:
                                del local_connections["docker"]
                                print("Docker not available locally")
                return local_connections

        @staticmethod
        def resolve_local_path(path):
                path = os.path.abspath(path)
                if not HostManager.running_in_container:
                        return path
                else:
                        for host_path, container_path in HostManager.container_volumes.items():
                                if container_path in path:
                                        return os.path.join(host_path, path[len(container_path)+1:])
                        logging.getLogger("HostManager").warning("Trying to resolve %s but no binding as been found" % path)
                        return path