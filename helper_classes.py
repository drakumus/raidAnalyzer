import datetime
import json
import pandas as pd
import plotly.express as px
from dash import dcc
import kaleido
import matplotlib.pyplot as plt
import numpy as np
from dataclasses import dataclass

import requests
from discord import Embed

# get encounters json
encounters_file = open('encounters.json')
encounter_data = json.load(encounters_file)

session_data = {
    "startTime": float(datetime.datetime.now().timestamp()),
    "endTime": float(0),
    "clearRate": 0,
    "encounters": []
}


def getEncounterData(trigger_id):
    for encounter in encounter_data:
        for boss in encounter['bosses']:
            if trigger_id == encounter['bosses'][boss]:
                return encounter


def print_plural(number, between):
    return f'{number}{between}{"s" if number > 1 else ""}'


@dataclass
class Boss:
    logUrl: str
    duration: datetime.timedelta
    startTime: datetime.datetime
    endTime: datetime.datetime
    name: str
    cm: bool
    compDps: int
    wing_str: str
    totalStartTime: datetime.datetime
    totalEndTime: datetime.datetime
    success: bool = False
    num_pulls: int = 1

    def addPull(self, pull):
        if self.success:
            self.num_pulls += 1
        else:
            # if the duration is longer on fail it's a better pull, otherwise return
            if self.duration > pull.duration:
                self.num_pulls += 1
                return

            # update boss with better pull
            self.logUrl = pull.logUrl
            self.duration = pull.duration
            self.startTime = pull.startTime
            self.endTime = pull.endTime
            self.name = pull.name
            self.cm = pull.cm
            self.compDps = pull.compDps
            self.wing_str = pull.wing_str
            if pull.startTime < self.totalStartTime:
                self.totalStartTime = pull.startTime
            if pull.endTime > self.totalEndTime:
                self.totalEndTime = pull.endTime
            self.startTime = pull.startTime
            self.endTime = pull.endTime
            self.success = pull.success
            self.num_pulls += 1

    def getEmbedString(self):
        # 0:00:00 Quadim the Peerless
        #    05:41 kill time, 1 pull, 178k comp dps
        minutes = self.duration.seconds // 60
        seconds = self.duration.seconds % 60
        return f'[{self.name}{" CM" if self.cm else ""}]({self.logUrl})' \
               f' {"{:02}:{:02}".format(minutes, seconds)} kill time, {print_plural(self.num_pulls, " pull")}, {self.compDps // 1000}k comp dps'

    def __str__(self):
        duration_string = f'{print_plural(self.duration.seconds // 60, " min")} {print_plural(self.duration.seconds % 60, " sec")}'
        return f'**{self.name}{" CM" if self.cm else ""}** for {duration_string}' \
               f' ({print_plural(self.num_pulls, " pull")}, {self.compDps // 1000}k comp dps): {self.logUrl}'

    def __repr__(self):
        return self.startTime


class Wing:
    bosses: [Boss]
    startTime: datetime.datetime
    endTime: datetime.datetime
    duration: datetime.timedelta
    wingString: str

    def __init__(self, bosses):
        self.bosses = []
        current_boss: Boss = None
        for boss in bosses:
            if current_boss is None:
                current_boss = boss
                continue
            if current_boss.name != boss.name:
                self.bosses.append(current_boss)
                current_boss = boss
            else:
                current_boss.addPull(boss)
        self.bosses.append(current_boss)
        self.startTime = self.bosses[0].startTime
        self.endTime = self.bosses[-1].endTime
        self.duration = self.endTime - self.startTime
        self.wingString = self.bosses[0].wing_str

    def getEmbedString(self, session_start_time: datetime.datetime):
        output_string = ""
        for boss in self.bosses:
            start_time = boss.startTime - session_start_time
            hours = start_time.seconds // 3600
            minutes = (start_time.seconds % 3600) // 60
            seconds = start_time.seconds % 60
            output_string += f'{"{:1}:{:02}:{:02}".format(hours, minutes, seconds)} {boss.getEmbedString()}\n'
        return output_string

    def __str__(self):
        hrs = print_plural(self.duration.seconds // 3600, " hr")
        mints = print_plural(self.duration.seconds // 60, " min")
        secs = print_plural(self.duration.seconds % 60, " sec")
        out = f'**{self.wingString}** for {hrs + " " if self.duration.seconds // 3600 > 0 else ""}{mints} {secs}\n'
        for boss in self.bosses:
            out += f'{str(boss)}\n'
        return out


class Session:
    startTime: datetime.datetime
    endTime: datetime.datetime
    duration: datetime.timedelta
    wings: [Wing] = []

    def addLogs(self, dps_report_urls: []):
        bosses = []
        # store relevant log data
        for log_url in dps_report_urls:
            dps_report_metadata = requests.get('https://dps.report/getUploadMetadata', params={'permalink': log_url})
            log_metadata_json = dps_report_metadata.json()
            encounter_metadata = log_metadata_json['encounter']
            encounter_clarification = getEncounterData(encounter_metadata['bossId'])

            log_start_time = datetime.datetime.fromtimestamp(log_metadata_json["encounterTime"])
            log_end_time = log_start_time + datetime.timedelta(seconds=encounter_metadata['duration'])
            boss = Boss(logUrl=log_url,
                        duration=datetime.timedelta(seconds=encounter_metadata['duration']),
                        startTime=log_start_time,
                        endTime=log_end_time,
                        name=encounter_metadata["boss"],
                        cm=encounter_metadata["isCm"],
                        compDps=encounter_metadata["compDps"],
                        wing_str=f'Wing {encounter_clarification["categories"][1]}',
                        success=encounter_metadata["success"],
                        num_pulls=1,
                        totalStartTime=log_start_time,
                        totalEndTime=log_end_time)
            bosses.append(boss)
        sorted_bosses = sorted(bosses, key=lambda b: b.startTime)
        # move bosses into wings
        wing_bosses = []
        for boss in sorted_bosses:
            if len(wing_bosses) == 0:
                wing_bosses.append(boss)
            else:
                if boss.wing_str != wing_bosses[0].wing_str:
                    self.wings.append(Wing(wing_bosses))
                    wing_bosses = [boss]
                else:
                    wing_bosses.append(boss)
        self.wings.append(Wing(wing_bosses))
        self.startTime = sorted_bosses[0].startTime
        self.endTime = sorted_bosses[-1].endTime
        self.duration = self.endTime - self.startTime

    def getGnattGraph(self):
        dataframe_input: [dict] = []
        for wing in self.wings:
            for boss in wing.bosses:
                dataframe_input.append({
                    "name": boss.name,
                    "startTime": boss.totalStartTime,
                    "endTime": boss.totalEndTime,
                    "Num Pulls": boss.num_pulls,
                    "wing": boss.wing_str
                })
        boss_dataframe = pd.DataFrame.from_records(dataframe_input)
        fig = px.timeline(
            boss_dataframe,
            x_start="startTime",
            x_end="endTime",
            y="Num Pulls",
            color="wing",
            text="name",
            width=1600,
            height=800,
            template='simple_white')
        fig.update_yaxes(type="category")
        fig.update_traces(textposition='inside')
        fig.update_layout(uniformtext_minsize=20, uniformtext_mode='hide',
                          title="Weekly Clear Gnatt Graph",
                          xaxis_title="Time",
                          yaxis_title="Num Pulls",
                          legend_title="Wings",
                          font=dict(
                              size=24
                          ))
        dcc.Graph(figure=fig)
        image = fig.to_image(format="png")
        # fig.write_image(file="test1.png", format="png", scale=2)
        # fig.show()

    def getRichEmbed(self):
        embed = Embed(color=0x008080)
        embed.title = f'{self.startTime.strftime("%m/%d/%y")} Session Total Time: {str(self.duration)[:-4]}'
        index = 0
        for wing in self.wings:
            wing_embed_string = wing.getEmbedString(self.startTime)
            if index < len(self.wings) - 1:
                duration = self.wings[index + 1].startTime - wing.endTime
                duration_mins = (duration.seconds % 3600) // 60
                duration_secs = duration.seconds % 60
                start_time = wing.endTime - self.startTime
                hours = start_time.seconds // 3600
                minutes = (start_time.seconds % 3600) // 60
                seconds = start_time.seconds % 60

                wing_embed_string += f'{"{:1}:{:02}:{:02}".format(hours, minutes, seconds)} Between ' \
                                     f'{"{:02}:{:02}".format(duration_mins, duration_secs)}'
            hours = wing.duration.seconds // 3600
            minutes = (wing.duration.seconds % 3600) // 60
            seconds = wing.duration.seconds % 60
            hours_str = print_plural(hours, " hr")
            minutes_str = print_plural(minutes, " min")
            seconds_str = print_plural(seconds, " sec")
            embed.add_field(
                name=f'{wing.wingString}: {f"{hours_str} " if hours > 0 else ""}{minutes_str} {seconds_str}',
                value=wing_embed_string,
                inline=False)

            index += 1
        return embed

    def __str__(self):
        duration_str = str(self.duration)[:-4]
        out = f'This session took {duration_str}\n'
        for wing in self.wings:
            out += str(wing)
        return out
