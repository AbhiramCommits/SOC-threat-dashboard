import json
import uuid
from datetime import datetime, timedelta, timezone
from random import choice, randint

import numpy as np

STIX_VERSION = "2.1"

TACTICS = [
    ("reconnaissance", "ta0043"),
    ("resource-development", "ta0042"),
    ("initial-access", "ta0001"),
    ("execution", "ta0002"),
    ("persistence", "ta0003"),
    ("privilege-escalation", "ta0004"),
    ("defense-evasion", "ta0005"),
    ("credential-access", "ta0006"),
    ("discovery", "ta0007"),
    ("lateral-movement", "ta0008"),
    ("collection", "ta0009"),
    ("command-and-control", "ta0011"),
    ("exfiltration", "ta0010"),
    ("impact", "ta0040"),
]

ALERT_NARRATIVES = [
    "Detected outbound traffic to known C2 IP over port 443",
    "Multiple failed login attempts from external IP {ip} against admin account",
    "Suspicious PowerShell execution detected on host {hostname}",
    "Unexpected DNS query for DGA domain {domain} observed",
    "Phishing email with malicious attachment delivered to {target}",
    "Registry persistence key added under HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    "New local user account created with administrative privileges on {hostname}",
    "Scheduled task created to execute obfuscated script at {hostname}",
    "LSASS process memory dump detected via procdump-like behavior on {hostname}",
    "Anomalous RDP connection from external IP {ip} to domain controller",
    "Outbound SSH tunnel detected from {hostname} to external host on port 22",
    "Data staging observed in temporary directory on {hostname}",
    "Large volume of outbound FTP traffic from {hostname} to external IP {ip}",
    "Web shell upload attempt detected on {hostname} at /uploads/ directory",
    "Privilege escalation via UAC bypass detected on {hostname}",
    "Kernel driver loaded to disable endpoint protection on {hostname}",
    "Brute-force attack on SMB share {share} from internal host {hostname}",
    "Network scan sweep detected from IP {ip} across multiple subnets",
    "Unusual child process spawned by msbuild.exe on {hostname}",
    "Credential dumping via mimikatz detected on {hostname}",
    "Outbound connection to TOR exit node from {hostname}",
    "WMI persistence established via __EventFilter on {hostname}",
    "Suspected Kerberoasting attack targeting service account {target}",
    "Domain trust enumeration via netdom on {hostname}",
    "Abnormal process injection into svchost.exe on {hostname}",
    "Keylogging activity detected on {hostname}",
    "Exfiltration over DNS tunnel observed from {hostname}",
    "Targeted spear-phishing campaign against finance department user {target}",
    "Suspected supply chain compromise in third-party software on {hostname}",
    "Living-off-the-land binary (LOLBin) execution of certutil on {hostname}",
    "Pass-the-hash authentication detected from {hostname} to domain controller",
    "Active Directory object deletion spree detected on domain controller",
    "Ransomware file extension change observed on {hostname}",
    "Encrypted malicious payload decoded and executed in memory on {hostname}",
    "Outbound Cobalt Strike beaconing pattern detected from {hostname}",
    "Suspicious PowerShell download cradle on {hostname}",
    "Bootkit installation attempted via MBR modification on {hostname}",
    "Cloud metadata API accessed from {hostname} in non-standard way",
    "Container escape attempt detected on {hostname}",
    "Privileged container launched with hostPID: true on {hostname}",
    "Kubernetes service account token theft detected from pod {hostname}",
    "AWS access key exfiltration via instance metadata service on {hostname}",
    "Unexpected security group modification adding 0.0.0.0/0 ingress on {hostname}",
    "Suspected Golden Ticket attack with forged TGT for {target}",
    "DCShadow attack attempting rogue domain controller replication on {hostname}",
    "Skeleton key malware installed on domain controller {hostname}",
    "Network traffic tunneling over ICMP from {hostname} to external IP {ip}",
    "VNC remote access tool deployed without authorization on {hostname}",
    "Browser credential theft via access to Chrome Login Data on {hostname}",
    "SAML token forgery detected in authentication logs for {target}",
]


def gen_ip():
    return ".".join(str(randint(1, 254)) for _ in range(4))


def gen_hostname():
    prefixes = ["srv", "dc", "web", "db", "dev", "ops", "fin", "hr", "lab", "ws"]
    return f"{choice(prefixes)}-{randint(10, 999):03d}"


def gen_domain():
    suffixes = [".xyz", ".top", ".biz", ".info", ".cc", ".tk", ".ml", ".ga", ".cf", ".gq"]
    return f"{uuid.uuid4().hex[:10]}{choice(suffixes)}"


def fill_template(narrative):
    result = narrative
    while "{ip}" in result:
        result = result.replace("{ip}", gen_ip(), 1)
    while "{hostname}" in result:
        result = result.replace("{hostname}", gen_hostname(), 1)
    while "{domain}" in result:
        result = result.replace("{domain}", gen_domain(), 1)
    while "{target}" in result:
        targets = ["jsmith@corp.com", "admin@corp.com", "finance-team@corp.com", "svc_backup@corp.com", "ceo@corp.com"]
        result = result.replace("{target}", choice(targets), 1)
    while "{share}" in result:
        shares = ["\\\\DC01\\Finance", "\\\\DC01\\HR", "\\\\DC01\\IT", "\\\\DC01\\Engineering"]
        result = result.replace("{share}", choice(shares), 1)
    return result


def generate_bundles(count=100):
    np.random.seed(42)
    bundles = []

    for i in range(count):
        tactic_name, tactic_id = TACTICS[i % len(TACTICS)]
        narrative_template = choice(ALERT_NARRATIVES)
        raw_text = fill_template(narrative_template)
        timestamp = (
            datetime.now(timezone.utc)
            - timedelta(days=randint(0, 90), hours=randint(0, 23), minutes=randint(0, 59))
        ).isoformat()

        indicator_id = f"indicator--{uuid.uuid4()}"
        observed_id = f"observed-data--{uuid.uuid4()}"
        identity_id = f"identity--{uuid.uuid4()}"
        marking_id = f"marking-definition--{uuid.uuid4()}"
        relationship_id = f"relationship--{uuid.uuid4()}"
        bundle_id = f"bundle--{uuid.uuid4()}"

        indicator = {
            "type": "indicator",
            "spec_version": STIX_VERSION,
            "id": indicator_id,
            "created": timestamp,
            "modified": timestamp,
            "name": f"Alert indicator for {tactic_name.replace('-', ' ').title()}",
            "description": raw_text,
            "indicator_types": ["malicious-activity"],
            "pattern": f"[file:hashes.'SHA-256' = '{uuid.uuid4().hex}']",
            "pattern_type": "stix",
            "valid_from": timestamp,
            "labels": [tactic_name],
            "external_references": [
                {
                    "source_name": "mitre-attack",
                    "external_id": tactic_id,
                    "url": f"https://attack.mitre.org/tactics/{tactic_id}/",
                }
            ],
        }

        observed = {
            "type": "observed-data",
            "spec_version": STIX_VERSION,
            "id": observed_id,
            "created": timestamp,
            "modified": timestamp,
            "first_observed": timestamp,
            "last_observed": timestamp,
            "number_observed": randint(1, 1000),
            "objects": {
                "0": {"type": "ipv4-addr", "value": gen_ip()},
                "1": {"type": "domain-name", "value": gen_domain()},
            },
        }

        identity = {
            "type": "identity",
            "spec_version": STIX_VERSION,
            "id": identity_id,
            "created": timestamp,
            "modified": timestamp,
            "name": "SOC Threat Dashboard",
            "identity_class": "organization",
        }

        marking = {
            "type": "marking-definition",
            "spec_version": STIX_VERSION,
            "id": marking_id,
            "created": timestamp,
            "definition_type": "statement",
            "definition": {"statement": "Copyright 2024 SOC Dashboard. All rights reserved."},
        }

        relationship = {
            "type": "relationship",
            "spec_version": STIX_VERSION,
            "id": relationship_id,
            "created": timestamp,
            "modified": timestamp,
            "relationship_type": "indicates",
            "source_ref": indicator_id,
            "target_ref": observed_id,
        }

        bundle = {
            "type": "bundle",
            "id": bundle_id,
            "objects": [indicator, observed, identity, marking, relationship],
            "metadata": {
                "tactic": tactic_name,
                "tactic_id": tactic_id,
                "raw_text": raw_text,
                "timestamp": timestamp,
            },
        }
        bundles.append(bundle)

    return bundles


def main():
    bundles = generate_bundles(100)
    output_path = "data/sample_stix_feed.json"
    with open(output_path, "w") as f:
        json.dump(bundles, f, indent=2)
    print(f"Generated {len(bundles)} STIX 2.1 bundles -> {output_path}")


if __name__ == "__main__":
    main()
