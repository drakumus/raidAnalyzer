from discord import Webhook, SyncWebhook, Embed
from helper_classes import Session

# get logs
logs_file = open('logs.txt', 'r')
logs_file_lines = logs_file.readlines()
logs = []
for line in logs_file_lines:
    logs.append(line.strip())

session = Session()
session.addLogs(logs)
session.getGnattGraph()
print(session)

# webhook = SyncWebhook.from_url('https://discord.com/api/webhooks/1075531508930052187/j_rvETKZVkvsnFCZQFKezWCFgnao3N2N_hIJFTmB9CcOhDtJH5Ux71JaF33Fe_ljQaCD')
webhook = SyncWebhook.from_url('https://discord.com/api/webhooks/1075247451457470474/Hdd2s4ropq64DzG6O7I4jH1kcD172pRR3dfD9lxBV_PBEtXcUS2bRZesfioJLFasWinn')
webhook.send(embed=session.getRichEmbed(), username='Session Analyzer')

