import sys
import pynetbox

from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_command
from nornir.core.task import Task, Result

nr = InitNornir(config_file="/home/admin/python/nornir/inventory/nornir_csv.yaml")

# setup NetBox API Session from Nornir config we imported above
nb = pynetbox.api(nr.config.inventory.options['nb_url'], nr.config.inventory.options['nb_token'], nr.config.inventory.options['ssl_verify'])

# Find the system in NetBox using the NorNir inventory plugin
nr = nr.filter(name=sys.argv[1])
print(nr.inventory.hosts)

# Need to get device to update platform -> using pynetbox with the "nb" object defined above
device = nb.dcim.devices.get(name=sys.argv[1])

# set current platform to 'linux' in NetBox --> so netmiko can connect
device.update({"device": device, "platform": 6})

# Need to refilter after making the change to the platform -> otherwise SSH fails
nr = InitNornir(config_file="/home/admin/python/nornir/inventory/nornir_csv.yaml")
nr = nr.filter(name=sys.argv[1])

# Find the current version of software installed on the switch -> update NetBox
platform_name = nr.run(task=netmiko_send_command, command_string="show version |  grep Software")
platform_name = platform_name[device.name][0].result.split(":")[1].strip()

# Sanity Check to make sure we are on correct device -> IP's change all the time
device_serial = nr.run(task=netmiko_send_command, command_string="show version |  grep Serial")
device_serial = device_serial[device.name][0].result.split(":")[1].strip()

if device.serial == device_serial:
    print("The device serial number matches what is in NetBox. Safe to move forward.")

    # Restore the platform with the info from the switch -> current OS version
    device_platfrom = nb.dcim.platforms.get(name=platform_name)
    
    # Create the platform if missing
    if not device_platfrom:
        platform_slug = platform_name.lower().replace(".","-")
        nb.dcim.platforms.create(name=platform_name, slug=platform_slug)
        device_platfrom = nb.dcim.platforms.get(name=platform_name)

    device = nb.dcim.devices.get(name=sys.argv[1])
    device.update({"device": device, "platform": device_platfrom.id})
    device.save()

    # Take this opportunity to ensure the mac addresses are accounted for
    eth0_mac = nr.run(task=netmiko_send_command, command_string="sudo ifconfig eth0 | grep ether | awk '{print $2}' ")
    eth0_mac = eth0_mac[device.name][0].result.strip()
    print(f"eth0 mac: {eth0_mac}")

    eth0_id = nb.dcim.interfaces.get(device=device.name, name="eth0").id
    mac_address = nb.dcim.interfaces.get(device=device.name, name="eth0").mac_address

    if mac_address is None:
        try:
            nb.dcim.mac_addresses.create({"mac_address": eth0_mac, "device": device.name, "interface": "eth0", "assigned_object_type": "dcim.interface" , "assigned_object_id": eth0_id, "is_primary": True })
  
            mac_id = nb.dcim.mac_addresses.get(device=device.name, interface="eth0").id

            mac = nb.dcim.interfaces.get(device = device.name, name="eth0")
            mac.update({"mac_address": eth0_mac, "primary_mac_address": mac_id})
            mac.save()
        except Exception as e:
            print(f"An error occurred: {e}")
    
    # set the BMC mac address as well
    bmc_mac = nr.run(task=netmiko_send_command, command_string="sudo ipmitool lan print | grep 'MAC Address' | awk '{print $4}' ")
    bmc_mac = bmc_mac[device.name][0].result.strip()
    print(f"bmc mac: {bmc_mac}")

    bmc_id = nb.dcim.interfaces.get(device=device.name, name="bmc").id
    bmc_mac_address = nb.dcim.interfaces.get(device=device.name, name="bmc").mac_address
    
    if bmc_mac_address is None:
        try:
            nb.dcim.mac_addresses.create({"mac_address": bmc_mac, "device": device.name, "interface": "bmc", "assigned_object_type": "dcim.interface" , "assigned_object_id": bmc_id, "is_primary": True })
  
            bmc_mac_id = nb.dcim.mac_addresses.get(device=device.name, interface="bmc").id

            bmc_mac = nb.dcim.interfaces.get(device = device.name, name="bmc")
            bmc_mac.update({"mac_address": eth0_mac, "primary_mac_address": bmc_mac_id})
            bmc_mac.save()
        except Exception as e:
            print(f"An error occurred: {e}")

else:
    print("Check the IP address -> The device serial does not match the NetBox device Serial.")
