"""Create an original temporary 48 kHz timing track using the standard library."""
import array
import math
import random
import sys
import wave
from pathlib import Path

out = Path(__file__).resolve().parent / 'review' / 'timing-track.wav'
rate = 48000
rng = random.Random(77)
samples = array.array('h')
low_noise = 0.0
impact = 89 / 25  # Blender frame 90, counting the first frame as time zero.
for n in range(rate*6):
    t = n/rate
    noise = rng.uniform(-1,1)
    low_noise += .04*(noise-low_noise)
    v = .042*math.sin(2*math.pi*44*t)*min(1,t/1.4)*math.exp(-max(0,t-impact)*2)
    if .85 < t < impact:
        p = (t-.85)/(impact-.85)
        v += p*p*(.17*low_noise+.033*math.sin(2*math.pi*(83*t+29*t*t)))
    for beat in (1.84,2.04,2.32,2.60,2.88,3.16,3.33):
        dt = t-beat
        if 0 <= dt < .2:
            v += .17*math.exp(-dt*80)*(noise*.45+math.sin(2*math.pi*1340*dt)*.55)
    dt = t-impact
    if dt >= 0:
        v += .52*math.exp(-dt*3.3)*math.sin(2*math.pi*(47*dt+2.2*(1-math.exp(-dt*22))))
        v += .24*math.exp(-dt*10)*low_noise
        v += .09*math.exp(-dt*3.8)*math.sin(2*math.pi*887*dt)
    samples.append(round(32767*max(-.95,min(.95,v))*min(1,(6-t)/.15)))
if sys.byteorder != 'little':
    samples.byteswap()
with wave.open(str(out),'wb') as f:
    f.setparams((1,2,rate,0,'NONE','not compressed'))
    f.writeframes(samples.tobytes())
