# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.resource.detector.azure.vm import AzureVMResourceDetector

LINUX_JSON = (
    "\n"
    "{\n"
    '    "additionalCapabilities": {\n'
    '        "hibernationEnabled": "false"\n'
    "    },\n"
    '    "azEnvironment": "AzurePublicCloud",\n'
    '    "customData": "",\n'
    '    "evictionPolicy": "",\n'
    '    "extendedLocation": {\n'
    '        "name": "",\n'
    '        "type": ""\n'
    "    },\n"
    '    "host": {\n'
    '        "id": ""\n'
    "    },\n"
    '    "hostGroup": {\n'
    '        "id": ""\n'
    "    },\n"
    '    "isHostCompatibilityLayerVm": "true",\n'
    '    "licenseType": "",\n'
    '    "location": "westus",\n'
    '    "name": "examplevmname",\n'
    '    "offer": "0001-com-ubuntu-server-focal",\n'
    '    "osProfile": {\n'
    '        "adminUsername": "azureuser",\n'
    '        "computerName": "examplevmname",\n'
    '        "disablePasswordAuthentication": "true"\n'
    "    },\n"
    '    "osType": "Linux",\n'
    '    "placementGroupId": "",\n'
    '    "plan": {\n'
    '        "name": "",\n'
    '        "product": "",\n'
    '        "publisher": ""\n'
    "    },\n"
    '    "platformFaultDomain": "0",\n'
    '    "platformSubFaultDomain": "",\n'
    '    "platformUpdateDomain": "0",\n'
    '    "priority": "",\n'
    '    "provider": "Microsoft.Compute",\n'
    '    "publicKeys": [\n'
    "        {\n"
    '            "keyData": "ssh-rsa 0",\n'
    '            "path": "/home/user/.ssh/authorized_keys0"\n'
    "        },\n"
    "        {\n"
    '            "keyData": "ssh-rsa 1",\n'
    '            "path": "/home/user/.ssh/authorized_keys1"\n'
    "        }\n"
    "    ],\n"
    '    "publisher": "canonical",\n'
    '    "resourceGroupName": "macikgo-test-may-23",\n'
    '    "resourceId": "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23/providers'
    '/Microsoft.Compute/virtualMachines/examplevmname",\n'
    '    "securityProfile": {\n'
    '        "encryptionAtHost": "false",\n'
    '        "secureBootEnabled": "true",\n'
    '        "securityType": "TrustedLaunch",\n'
    '        "virtualTpmEnabled": "true"\n'
    "    },\n"
    '    "sku": "20_04-lts-gen2",\n'
    '    "storageProfile": {\n'
    '        "dataDisks": [\n'
    "            {\n"
    '                "bytesPerSecondThrottle": "979202048",\n'
    '                "caching": "None",\n'
    '                "createOption": "Empty",\n'
    '                "diskCapacityBytes": "274877906944",\n'
    '                "diskSizeGB": "1024",\n'
    '                "image": {\n'
    '                    "uri": ""\n'
    "                },\n"
    '                "isSharedDisk": "false",\n'
    '                "isUltraDisk": "true",\n'
    '                "lun": "0",\n'
    '                "managedDisk": {\n'
    '                    "id": "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23/p'
    'roviders/Microsoft.Compute/disks/exampledatadiskname",\n'
    '                    "storageAccountType": "StandardSSD_LRS"\n'
    "                },\n"
    '                "name": "exampledatadiskname",\n'
    '                "opsPerSecondThrottle": "65280",\n'
    '                "vhd": {\n'
    '                    "uri": ""\n'
    "                },\n"
    '                "writeAcceleratorEnabled": "false"\n'
    "            }\n"
    "        ],\n"
    '        "imageReference": {\n'
    '            "id": "",\n'
    '            "offer": "0001-com-ubuntu-server-focal",\n'
    '            "publisher": "canonical",\n'
    '            "sku": "20_04-lts-gen2",\n'
    '            "version": "latest"\n'
    "        },\n"
    '        "osDisk": {\n'
    '            "caching": "ReadWrite",\n'
    '            "createOption": "FromImage",\n'
    '            "diffDiskSettings": {\n'
    '                "option": ""\n'
    "            },\n"
    '            "diskSizeGB": "30",\n'
    '            "encryptionSettings": {\n'
    '                "enabled": "false",\n'
    '                "diskEncryptionKey": {\n'
    '                    "sourceVault": {\n'
    '                        "id": "/subscriptions/test-source-guid/resourceGroups/testrg/providers/Microsoft.KeyVau'
    'lt/vaults/test-kv"\n'
    "                    },\n"
    '                    "secretUrl": "https://test-disk.vault.azure.net/secrets/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/xx'
    'xxx-xxxx-xxxx-xxxx-xxxxxxxxxxx"\n'
    "                },\n"
    '                "keyEncryptionKey": {\n'
    '                    "sourceVault": {\n'
    '                        "id": "/subscriptions/test-key-guid/resourceGroups/testrg/providers/Microsoft.KeyVault/'
    'vaults/test-kv"\n'
    "                    },\n"
    '                    "keyUrl": "https://test-key.vault.azure.net/secrets/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/xxxxx-'
    'xxxx-xxxx-xxxx-xxxxxxxxxxx"\n'
    "                }\n"
    "            },\n"
    '            "image": {\n'
    '                "uri": ""\n'
    "            },\n"
    '            "managedDisk": {\n'
    '                "id": "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23/provi'
    'ders/Microsoft.Compute/disks/exampleosdiskname",\n'
    '                "storageAccountType": "StandardSSD_LRS"\n'
    "            },\n"
    '            "name": "exampledatadiskname",\n'
    '            "osType": "Linux",\n'
    '            "vhd": {\n'
    '                "uri": ""\n'
    "            },\n"
    '            "writeAcceleratorEnabled": "false"\n'
    "        },\n"
    '        "resourceDisk": {\n'
    '            "size": "16384"\n'
    "        }\n"
    "    },\n"
    '    "subscriptionId": "xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx",\n'
    '    "tags": "azsecpack:nonprod;platformsettings.host_environment.service.platform_optedin_for_rootcerts:true",'
    "\n"
    '    "tagsList": [\n'
    "        {\n"
    '            "name": "azsecpack",\n'
    '            "value": "nonprod"\n'
    "        },\n"
    "        {\n"
    '            "name": "platformsettings.host_environment.service.platform_optedin_for_rootcerts",\n'
    '            "value": "true"\n'
    "        }\n"
    "    ],\n"
    '    "userData": "",\n'
    '    "version": "20.04.202307240",\n'
    '    "virtualMachineScaleSet": {\n'
    '        "id": "/subscriptions/xxxxxxxx-xxxxx-xxx-xxx-xxxx/resourceGroups/resource-group-name/providers/Microsof'
    't.Compute/virtualMachineScaleSets/virtual-machine-scale-set-name"\n'
    "    },\n"
    '    "vmId": "02aab8a4-74ef-476e-8182-f6d2ba4166a6",\n'
    '    "vmScaleSetName": "crpteste9vflji9",\n'
    '    "vmSize": "Standard_A3",\n'
    '    "zone": "1"\n'
    "}\n"
    ""
)
WINDOWS_JSON = (
    "\n"
    "{\n"
    '    "additionalCapabilities": {\n'
    '        "hibernationEnabled": "false"\n'
    "    },\n"
    '    "azEnvironment": "AzurePublicCloud",\n'
    '    "customData": "",\n'
    '    "evictionPolicy": "",\n'
    '    "extendedLocation": {\n'
    '        "name": "",\n'
    '        "type": ""\n'
    "    },\n"
    '    "host": {\n'
    '        "id": ""\n'
    "    },\n"
    '    "hostGroup": {\n'
    '        "id": ""\n'
    "    },\n"
    '    "isHostCompatibilityLayerVm": "true",\n'
    '    "licenseType": "Windows_Client",\n'
    '    "location": "westus",\n'
    '    "name": "examplevmname",\n'
    '    "offer": "WindowsServer",\n'
    '    "osProfile": {\n'
    '        "adminUsername": "azureuser",\n'
    '        "computerName": "examplevmname",\n'
    '        "disablePasswordAuthentication": "true"\n'
    "    },\n"
    '    "osType": "Windows",\n'
    '    "placementGroupId": "",\n'
    '    "plan": {\n'
    '        "name": "",\n'
    '        "product": "",\n'
    '        "publisher": ""\n'
    "    },\n"
    '    "platformFaultDomain": "0",\n'
    '    "platformSubFaultDomain": "",\n'
    '    "platformUpdateDomain": "0",\n'
    '    "priority": "",\n'
    '    "provider": "Microsoft.Compute",\n'
    '    "publicKeys": [\n'
    "        {\n"
    '            "keyData": "ssh-rsa 0",\n'
    '            "path": "/home/user/.ssh/authorized_keys0"\n'
    "        },\n"
    "        {\n"
    '            "keyData": "ssh-rsa 1",\n'
    '            "path": "/home/user/.ssh/authorized_keys1"\n'
    "        }\n"
    "    ],\n"
    '    "publisher": "RDFE-Test-Microsoft-Windows-Server-Group",\n'
    '    "resourceGroupName": "macikgo-test-may-23",\n'
    '    "resourceId": "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23/providers'
    '/Microsoft.Compute/virtualMachines/examplevmname",\n'
    '    "securityProfile": {\n'
    '        "encryptionAtHost": "false",\n'
    '        "secureBootEnabled": "true",\n'
    '        "securityType": "TrustedLaunch",\n'
    '        "virtualTpmEnabled": "true"\n'
    "    },\n"
    '    "sku": "2019-Datacenter",\n'
    '    "storageProfile": {\n'
    '        "dataDisks": [\n'
    "            {\n"
    '                "bytesPerSecondThrottle": "979202048",\n'
    '                "caching": "None",\n'
    '                "createOption": "Empty",\n'
    '                "diskCapacityBytes": "274877906944",\n'
    '                "diskSizeGB": "1024",\n'
    '                "image": {\n'
    '                    "uri": ""\n'
    "                },\n"
    '                "isSharedDisk": "false",\n'
    '                "isUltraDisk": "true",\n'
    '                "lun": "0",\n'
    '                "managedDisk": {\n'
    '                    "id": "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23/p'
    'roviders/Microsoft.Compute/disks/exampledatadiskname",\n'
    '                    "storageAccountType": "StandardSSD_LRS"\n'
    "                },\n"
    '                "name": "exampledatadiskname",\n'
    '                "opsPerSecondThrottle": "65280",\n'
    '                "vhd": {\n'
    '                    "uri": ""\n'
    "                },\n"
    '                "writeAcceleratorEnabled": "false"\n'
    "            }\n"
    "        ],\n"
    '        "imageReference": {\n'
    '            "id": "",\n'
    '            "offer": "WindowsServer",\n'
    '            "publisher": "MicrosoftWindowsServer",\n'
    '            "sku": "2019-Datacenter",\n'
    '            "version": "latest"\n'
    "        },\n"
    '        "osDisk": {\n'
    '            "caching": "ReadWrite",\n'
    '            "createOption": "FromImage",\n'
    '            "diffDiskSettings": {\n'
    '                "option": ""\n'
    "            },\n"
    '            "diskSizeGB": "30",\n'
    '            "encryptionSettings": {\n'
    '                "enabled": "false",\n'
    '                "diskEncryptionKey": {\n'
    '                    "sourceVault": {\n'
    '                        "id": "/subscriptions/test-source-guid/resourceGroups/testrg/providers/Microsoft.KeyVau'
    'lt/vaults/test-kv"\n'
    "                    },\n"
    '                    "secretUrl": "https://test-disk.vault.azure.net/secrets/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/xx'
    'xxx-xxxx-xxxx-xxxx-xxxxxxxxxxx"\n'
    "                },\n"
    '                "keyEncryptionKey": {\n'
    '                    "sourceVault": {\n'
    '                        "id": "/subscriptions/test-key-guid/resourceGroups/testrg/providers/Microsoft.KeyVault/'
    'vaults/test-kv"\n'
    "                    },\n"
    '                    "keyUrl": "https://test-key.vault.azure.net/secrets/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/xxxxx-'
    'xxxx-xxxx-xxxx-xxxxxxxxxxx"\n'
    "                }\n"
    "            },\n"
    '            "image": {\n'
    '                "uri": ""\n'
    "            },\n"
    '            "managedDisk": {\n'
    '                "id": "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23/provi'
    'ders/Microsoft.Compute/disks/exampleosdiskname",\n'
    '                "storageAccountType": "StandardSSD_LRS"\n'
    "            },\n"
    '            "name": "exampledatadiskname",\n'
    '            "osType": "Windows",\n'
    '            "vhd": {\n'
    '                "uri": ""\n'
    "            },\n"
    '            "writeAcceleratorEnabled": "false"\n'
    "        },\n"
    '        "resourceDisk": {\n'
    '            "size": "16384"\n'
    "        }\n"
    "    },\n"
    '    "subscriptionId": "xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx",\n'
    '    "tags": "azsecpack:nonprod;platformsettings.host_environment.service.platform_optedin_for_rootcerts:true",'
    "\n"
    '    "userData": "Zm9vYmFy",\n'
    '    "tagsList": [\n'
    "        {\n"
    '            "name": "azsecpack",\n'
    '            "value": "nonprod"\n'
    "        },\n"
    "        {\n"
    '            "name": "platformsettings.host_environment.service.platform_optedin_for_rootcerts",\n'
    '            "value": "true"\n'
    "        }\n"
    "    ],\n"
    '    "userData": "",\n'
    '    "version": "20.04.202307240",\n'
    '    "virtualMachineScaleSet": {\n'
    '        "id": "/subscriptions/xxxxxxxx-xxxxx-xxx-xxx-xxxx/resourceGroups/resource-group-name/providers/Microsof'
    't.Compute/virtualMachineScaleSets/virtual-machine-scale-set-name"\n'
    "    },\n"
    '    "vmId": "02aab8a4-74ef-476e-8182-f6d2ba4166a6",\n'
    '    "vmScaleSetName": "crpteste9vflji9",\n'
    '    "vmSize": "Standard_A3",\n'
    '    "zone": "1"\n'
    "}\n"
    ""
)
LINUX_ATTRIBUTES = {
    "azure.vm.scaleset.name": "crpteste9vflji9",
    "azure.vm.sku": "20_04-lts-gen2",
    "cloud.platform": "azure_vm",
    "cloud.provider": "azure",
    "cloud.region": "westus",
    "cloud.resource_id": (
        "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23"
        "/providers/Microsoft.Compute/virtualMachines/examplevmname"
    ),
    "host.id": "02aab8a4-74ef-476e-8182-f6d2ba4166a6",
    "host.name": "examplevmname",
    "host.type": "Standard_A3",
    "os.type": "Linux",
    "os.version": "20.04.202307240",
    "service.instance.id": "02aab8a4-74ef-476e-8182-f6d2ba4166a6",
}
WINDOWS_ATTRIBUTES = {
    "azure.vm.scaleset.name": "crpteste9vflji9",
    "azure.vm.sku": "2019-Datacenter",
    "cloud.platform": "azure_vm",
    "cloud.provider": "azure",
    "cloud.region": "westus",
    "cloud.resource_id": (
        "/subscriptions/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx/resourceGroups/macikgo-test-may-23"
        "/providers/Microsoft.Compute/virtualMachines/examplevmname"
    ),
    "host.id": "02aab8a4-74ef-476e-8182-f6d2ba4166a6",
    "host.name": "examplevmname",
    "host.type": "Standard_A3",
    "os.type": "Windows",
    "os.version": "20.04.202307240",
    "service.instance.id": "02aab8a4-74ef-476e-8182-f6d2ba4166a6",
}


class TestAzureVMResourceDetector(unittest.TestCase):
    @patch("opentelemetry.resource.detector.azure.vm.urlopen")
    def test_linux(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = LINUX_JSON
        attributes = AzureVMResourceDetector().detect().attributes
        for attribute_key, attribute_value in LINUX_ATTRIBUTES.items():
            self.assertEqual(attributes[attribute_key], attribute_value)

    @patch("opentelemetry.resource.detector.azure.vm.urlopen")
    def test_windows(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = WINDOWS_JSON
        attributes = AzureVMResourceDetector().detect().attributes
        for attribute_key, attribute_value in WINDOWS_ATTRIBUTES.items():
            self.assertEqual(attributes[attribute_key], attribute_value)

    @patch("opentelemetry.resource.detector.azure.vm._can_ignore_vm_detect")
    @patch("opentelemetry.resource.detector.azure.vm.urlopen")
    def test_in_another_rp(self, mock_urlopen, detect_mock):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = LINUX_JSON
        detect_mock.return_value = True
        attributes = AzureVMResourceDetector().detect().attributes
        self.assertEqual(attributes, {})
