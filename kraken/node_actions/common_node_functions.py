import time
import random
import logging
import paramiko
import kraken.kubernetes.client as kubecli
import kraken.invoke.command as runcommand


node_general = False


# Pick a random node with specified label selector
def get_node(node_name, label_selector, instance_kill_count):
    if node_name in kubecli.list_killable_nodes():
        return [node_name]
    elif node_name:
        logging.info("Node with provided node_name does not exist or the node might " "be in NotReady state.")
    nodes = kubecli.list_killable_nodes(label_selector)
    if not nodes:
        raise Exception("Ready nodes with the provided label selector do not exist")
    logging.info("Ready nodes with the label selector %s: %s" % (label_selector, nodes))
    number_of_nodes = len(nodes)
    if instance_kill_count == number_of_nodes:
        return nodes
    nodes_to_return = []
    for i in range(instance_kill_count):
        node_to_add = nodes[random.randint(0, len(nodes) - 1)]
        nodes_to_return.append(node_to_add)
        nodes.remove(node_to_add)
    return nodes_to_return


# Wait till node status becomes Ready
def wait_for_ready_status(node, timeout):
    for _ in range(timeout):
        if kubecli.get_node_status(node) == "Ready":
            break
        time.sleep(3)
        if kubecli.get_node_status(node) != "Ready":
            raise Exception("Node condition status isn't Ready")


# Wait till node status becomes NotReady
def wait_for_unknown_status(node, timeout):
    for _ in range(timeout):
        try:
            node_status = kubecli.get_node_status(node, timeout)
            if node_status is None or node_status == "Unknown":
                break
        except Exception:
            logging.error("Encountered error while getting node status, waiting 3 seconds and retrying")
        time.sleep(3)
    node_status = kubecli.get_node_status(node, timeout)
    logging.info("node status " + str(node_status))
    if node_status is not None and node_status != "Unknown":
        raise Exception("Node condition status isn't Unknown after %s seconds" % str(timeout))


# Get the ip of the cluster node
def get_node_ip(node):
    return runcommand.invoke(
        "kubectl get node %s -o " "jsonpath='{.status.addresses[?(@.type==\"InternalIP\")].address}'" % (node)
    )


def check_service_status(node, service, ssh_private_key, timeout):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    i = 0
    sleeper = 1
    while i <= timeout:
        try:
            time.sleep(sleeper)
            i += sleeper
            logging.info("Trying to ssh to instance: %s" % (node))
            connection = ssh.connect(
                node, username="root", key_filename=ssh_private_key, timeout=800, banner_timeout=400
            )
            if connection is None:
                break
        except Exception:
            pass
    for service_name in service:
        logging.info("Checking status of Service: %s" % (service_name))
        stdin, stdout, stderr = ssh.exec_command(
            "systemctl status %s  | grep '^   Active' " "|  awk '{print $2}'" % (service_name)
        )
        service_status = stdout.readlines()[0]
        logging.info("Status of service %s is %s \n" % (service_name, service_status.strip()))
        if service_status.strip() != "active":
            logging.error("Service %s is in %s state" % (service_name, service_status.strip()))
    ssh.close()
