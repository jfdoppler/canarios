import os, glob, peakutils, lmfit, time #emcee, 
import numpy as np
from matplotlib import cm
import matplotlib as mpl
import pandas as pd
from math import floor, ceil
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy import signal
from scipy.signal import argrelextrema
from scipy.signal import butter
from scipy.interpolate import interp1d
from sklearn.linear_model import LinearRegression
from matplotlib.gridspec import GridSpec
from scipy.signal import savgol_filter
from random import uniform
from numpy.polynomial import Polynomial
from multiprocessing import Pool
from scipy.signal import find_peaks
#import signal_envelope as se
#from scipy.signal import hilbert
#from scipy.interpolate import UnivariateSpline

def envelope_cabeza(signal, method='percentile', intervalLength=210, perc=90):
    """
    Calcula envolvente. En segmentos de intervalLength calcula el maximo
    (si no se especifica metodo) o el percentil especificado.
    """
    if method == 'percentile':        pp = perc
    else:                             pp = 100
    
    absSignal        = abs(signal)
    dt2              = int(intervalLength/2)
    outputSignal     = np.zeros(len(absSignal))
    outputSignal[0]  = absSignal[0]
    outputSignal[-1] = absSignal[-1]

    for baseIndex in range(1, len(absSignal)-1):
        if baseIndex < dt2:                     percentil = np.percentile(absSignal[:baseIndex], pp)
        elif baseIndex > len(absSignal) - dt2:  percentil = np.percentile(absSignal[baseIndex:], pp)
        else:                                   percentil = np.percentile(absSignal[baseIndex-dt2:baseIndex+dt2], pp)
        
        outputSignal[baseIndex] = percentil
    #print(np.shape(outputSignal))
    
    #analytic_signal = se(signal)
    #amplitude_envelope = se(signal)#np.abs(analytic_signal)
    #print(np.shape(amplitude_envelope))
    #print(np.shape(outputSignal))
    return outputSignal
    #return amplitude_envelope

def butter_lowpass(fs, lcutoff=3000.0, order=15):
    nyq            = 0.5*fs
    normal_lcutoff = lcutoff/nyq
    return butter(order, normal_lcutoff, btype='low', analog=False) # =bl, al

def butter_lowpass_filter(data, fs, lcutoff=3000.0, order=6):
    bl, al = butter_lowpass(fs, lcutoff, order=order)
    return  signal.filtfilt(bl, al, data)             # yl =
    
def butter_highpass(fs, hcutoff=100.0, order=6):
    nyq            = 0.5*fs
    normal_hcutoff = hcutoff/nyq
    return butter(order, normal_hcutoff, btype='high', analog=False)  # bh, ah =

def butter_highpass_filter(data, fs, hcutoff=100.0, order=5):
    bh, ah = butter_highpass(fs, hcutoff, order=order)
    return signal.filtfilt(bh, ah, data) #yh = 


def consecutive(data, stepsize=1, min_length=1):
    """
    Parte una tira de datos en bloques de datos consecutivos.
    Ej:
        [1,2,3,4,6,7,9,10,11] -> [[1,2,3,4],[6,7],[9,10,11]]
    """
    candidates = np.split(data, np.where(np.diff(data) != stepsize)[0]+1)
    return [x for x in candidates if len(x) > min_length]


def normalizar(arr, minout=-1, maxout=1, pmax=100, pmin=5, method='extremos'): #extremos
    """
    Normaliza un array en el intervalo minout-maxout
    """
    norm_array = np.copy(np.asarray(arr, dtype=np.double))
    if method == 'extremos':
        norm_array -= min(norm_array)
        norm_array = norm_array/max(norm_array)
        norm_array *= maxout-minout
        norm_array += minout
    elif method == 'percentil':
        norm_array -= np.percentile(norm_array, pmin)
        norm_array = norm_array/np.percentile(norm_array, pmax)
        norm_array *= maxout-minout
        norm_array += minout
    return norm_array


def get_spectrogram(data, sampling_rate, window=1024, overlap=1/1.1,
                    sigma=102.4, scale=0.000001):
    """
    Computa el espectrograma de la señal usando ventana gaussiana.

    sampling_rate = sampleo de la señal
    Window        = numero de puntos en la ventana
    overlap       = porcentaje de overlap entre ventanas
    sigma         = dispersion de la ventana

    Devuelve:

    tu = tiempos espectro
    fu = frecuencias
    Sxx = espectrograma

    Ejemplo de uso:
    tt, ff, SS = get_spectrogram(song, 44100)
    plt.pcolormesh(tt, ff, np.log(SS), cmap=plt.get_cmap('Greys'), rasterized=True)
    """
    fu, tu, Sxx = signal.spectrogram(data, sampling_rate, nperseg=window,
                                     noverlap=window*overlap,
                                     window=signal.get_window
                                     (('gaussian', sigma), window),
                                     scaling='spectrum')
    Sxx = np.clip(Sxx, a_min=np.amax(Sxx)*scale, a_max=np.amax(Sxx))
    return fu, tu, Sxx


def SpectralContent(data, fs, method='song', fmin=300, fmax=10000):#, dt_transit=0.002):
    segment = data # [int(dt_transit*fs):]
    fourier = np.abs(np.fft.rfft(segment))
    freqs   = np.fft.rfftfreq(len(segment), d=1/fs)
    min_bin = np.argmin(np.abs(freqs-fmin))
    max_bin = np.argmin(np.abs(freqs-fmax))
    fourier = np.abs(np.fft.rfft(segment))[min_bin:max_bin]
    
    freqs = np.fft.rfftfreq(len(segment), d=1/fs)[min_bin:max_bin]
    f_msf = np.sum(freqs*fourier)/np.sum(fourier)
    amp   = max(segment)-min(segment)
    f_aff = 0
    
    if method == 'song': 
        f_aff = freqs[np.argmax(fourier*(freqs/(freqs+500)**2))]
    elif method == 'syllable':
        orden = 10
        mm    = argrelextrema(segment, np.greater, order=orden)[0]
        difs  = np.diff(mm)
        while np.std(difs)/np.mean(difs) > 1/3 and orden > 1:
            orden -= 1
            mm     = argrelextrema(segment, np.greater, order=orden)[0]
            difs   = np.diff(mm)
        f_aff = fs / np.mean(np.diff(mm))
    elif method == 'synth':
        maximos = peakutils.indexes(fourier, thres=0.5, min_dist=5)
        if amp < 500:             f_aff = 0
        elif len(maximos) > 0:    f_aff = freqs[maximos[0]]
    return f_msf, f_aff, amp

def rk4(f, v, dt):
    k1 = f(v)    
    k2 = f(v + dt/2.0*k1)
    k3 = f(v + dt/2.0*k2)
    k4 = f(v + dt*k3)
    return v + dt*(2.0*(k2+k3)+k1+k4)/6.0
    
def sigmoid(x, dt=1, b=0, minout=0, maxout=1, fs=44100, rev=1):    
    return ((1/(1+np.exp(-((5/(dt*fs))*x+b))))*(maxout-minout)+minout)[::rev] # a = 5/(dt*fs), ax+b


def Windows(s, t, fs, window_time=0.05, overlap=1):
    window_chunck = floor(window_time*fs) # seconds*fs = NoDatos
    fraction      = np.size(s)/window_chunck
    window_new    = floor(window_chunck + (fraction%1)*window_chunck/(fraction//1))  # se podria usar ceil

    s_windowed = np.lib.stride_tricks.sliding_window_view(s, window_new)[::floor(overlap*window_new)] # overlap every
    t_windowed = np.lib.stride_tricks.sliding_window_view(t, window_new)[::floor(overlap*window_new)]
    
    return s_windowed, t_windowed

def FFandSCI(s, time, fs, t0, window_time=0.01, method='song'):
    Ndata = time.size
    s, t = Windows(s, time, fs, window_time=window_time)
    
    SCI,      time_ampl = np.zeros(np.shape(s)[0]), np.zeros(np.shape(s)[0])
    freq_amp, Ampl_freq = np.zeros(np.shape(s)[0]), np.zeros(np.shape(s)[0])
    
    for i in range(np.shape(s)[0]):
        amplitud_freq     = np.abs(np.fft.rfft(s[i]))
        freq = np.fft.rfftfreq(len(s[i]), d=1/fs)#[3:-3]
        
        # calculating peaks of fft
        #y    = amplitud_freq[3:-3] #np.abs(np.fft.rfft(s[i]))[5:-5]
        
        #peaks, _ = find_peaks(y, distance=20)#, height=np.max(y)/5)
        #if peaks.size!=0:  max1 = peaks[0]+3
        #else:              
        max1 = np.argmax(amplitud_freq)
        
        #maximos = peakutils.indexes(amplitud_freq, thres=0.05, min_dist=5)
        #if len(maximos)!=0: max1    = freq[maximos[0]]
        #else:               max1 = np.argmax(amplitud_freq)
        #else:  
            #max1 = np.argmax(amplitud_freq)
            #print(max1)
            
        
        f_msf, f_aff, amp = SpectralContent(s[i], fs, method=method, fmin=300, fmax=10000)
        #max1 = f_aff
        
        SCI[i]       = f_msf/f_aff
        time_ampl[i] = t[i,0]#floor(np.shape(t)[1]/2)] #window_length*i # left point
        freq_amp[i]  = f_aff#max1/window_time
        Ampl_freq[i] = np.amax(amplitud_freq)
    
    time_ampl += t0
    
    tim_inter       = np.linspace(time_ampl[0], time_ampl[-1], Ndata)  # time interpolated
    #time_ampl1 = time_ampl.reshape((-1,1)) # functions to interpolate
    
    model = LinearRegression().fit(time_ampl.reshape((-1,1)), freq_amp)
    
    inte_freq_amp   = interp1d(time_ampl, freq_amp) # = model.coef_*tim_inter+model.intercept_
    inte_Amp_freq   = interp1d(time_ampl, Ampl_freq) 
    # interpolate and smooth
    freq_amp_int = savgol_filter(inte_freq_amp(tim_inter), window_length=13, polyorder=3)
    Ampl_freq    = savgol_filter(inte_Amp_freq(tim_inter), window_length=13, polyorder=3)
    #print(np.shape(tim_inter), np.shape(freq_amp_int), np.shape(Ampl_freq))
    
    return SCI, time_ampl, freq_amp, Ampl_freq, freq_amp_int , tim_inter