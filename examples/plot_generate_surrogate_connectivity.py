#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as pl

from jumeg.jumeg_surrogates import Surrogates

from mne.connectivity import spectral_connectivity
from mne.datasets import sample
from mne.minimum_norm import read_inverse_operator, apply_inverse_epochs
import mne

data_path = sample.data_path()
subjects_dir = data_path + '/subjects'

fname_raw = data_path + '/MEG/sample/sample_audvis_filt-0-40_raw.fif'
fname_event = data_path + '/MEG/sample/sample_audvis_filt-0-40_raw-eve.fif'
fname_inv = data_path + '/MEG/sample/sample_audvis-meg-oct-6-meg-inv.fif'

raw = mne.io.read_raw_fif(fname_raw)
events = mne.read_events(fname_event)
inverse_operator = read_inverse_operator(fname_inv)

# add a bad channel
raw.info['bads'] += ['MEG 2443']

# pick MEG channels
picks = mne.pick_types(raw.info, meg=True, eeg=False, stim=False, eog=False,
                       exclude='bads')

# Define epochs for left-auditory condition
event_id, tmin, tmax = 1, -0.2, 0.5
epochs = mne.Epochs(raw, events, event_id, tmin, tmax, picks=picks,
                    baseline=(None, 0), reject=dict(mag=4e-12, grad=4000e-13))

snr = 1.0  # use lower SNR for single epochs
lambda2 = 1.0 / snr ** 2
method = "dSPM"  # use dSPM method (could also be MNE or sLORETA)
stcs = apply_inverse_epochs(epochs, inverse_operator, lambda2, method,
                            pick_ori="normal", return_generator=False)

# get labels for FreeSurfer 'aparc' cortical parcellation with 34 labels/hemi
labels = mne.read_labels_from_annot('sample', parc='aparc',
                                    subjects_dir=subjects_dir)
label_colors = [label.color for label in labels]

# average the source estimates within each label using sign-flips to reduce
# signal cancellations, also here we can return a generator
src = inverse_operator['src']
label_ts = mne.extract_label_time_course(stcs, labels, src, mode='mean_flip',
                                         return_generator=False)

# compute surrogates on the first STC extracted for 68 labels
n_surr = 5
fmin = 8.
fmax = 13.
sfreq = raw.info['sfreq']  # the sampling frequency
con_methods = ['coh', 'plv', 'wpli']
n_rois = len(labels)
full_surr_con = np.zeros((3, n_rois, n_rois, 1, n_surr))

real_con, freqs, times, n_epochs, n_tapers = spectral_connectivity(
    label_ts, method=con_methods, mode='fourier', sfreq=sfreq,
    fmin=fmin, fmax=fmax, faverage=True, mt_adaptive=True, n_jobs=4)

# loop through each of the label_ts from each epoch (i.e. 71)
# for my_label_ts in label_ts:
surr_ts = Surrogates(np.array(label_ts))
surr_ts.original_data.shape
surr_label_ts = surr_ts.compute_surrogates(n_surr=n_surr,
                                           return_generator=True)

for ind_surr, surr in enumerate(surr_label_ts):
    con, freqs, times, n_epochs, n_tapers = spectral_connectivity(
        surr, method=con_methods, mode='fourier', sfreq=sfreq,
        fmin=fmin, fmax=fmax, faverage=True, mt_adaptive=True, n_jobs=4)

    # con shape (method, n_signals, n_signals, n_freqs)
    full_surr_con[:, :, :, :, ind_surr] = con
    assert full_surr_con.flatten().max() <= 1., 'Maximum connectivity is above 1.'
    assert full_surr_con.flatten().min() >= 0., 'Minimum connectivity is 0.'

surr_ts.clear_cache()

# visualize the surrogates
# pl.plot(label_ts[0][0, :], 'b')
# for lts in surr_label_ts:
#     pl.plot(lts[0, :], 'r')
# pl.title('Extracted label time courses - real vs surrogates')
# pl.show()


def sanity_check_con_matrix(con):
    '''
    Check if the connectivity matrix provided satisfies necessary conditions.
    This is done to ensure that the data remains clean and spurious values are
    easily detected.
    Expected a connectivity matrix of shape
    (n_methods x n_rois x n_rois x n_freqs x n_surr)
    '''
    n_methods, n_rois, n_rois, n_freqs, n_surr = con.shape
    assert np.any(con), 'Matrix is not all zeros.'
    assert not (con == con[0]).all(), 'All rows are equal - methods not different.'
    for surr in range(1, n_surr):
        assert not (con[:, :, :, :, surr] == con[:, :, :, :, 0]).all(), 'All surrogates are equal.'
        assert not np.triu(con[0, :, :, 0, surr]).any(), 'Matrices not symmetric.'


sanity_check_con_matrix(full_surr_con)
