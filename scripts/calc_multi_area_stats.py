from glob import glob
from correlation_toolbox import helper as ch
from multiprocessing import Process
import json
import numpy as np
from os import path
from six import iteritems
from sys import argv

def pop_LvR(data_array, t_ref, t_min, t_max, num_neur):
    """
    Compute the LvR value of the given data_array.
    See Shinomoto et al. 2009 for details.

    Parameters
    ----------
    data_array : numpy.ndarray
        Arrays with spike data.
        column 0: neuron_ids, column 1: spike times
    t_ref : float
        Refractory period of the neurons.
    t_min : float
        Minimal time for the calculation.
    t_max : float
        Maximal time for the calculation.
    num_neur: int
        Number of recorded neurons. Needs to provided explicitly
        to avoid corruption of results by silent neurons not
        present in the given data.

    Returns
    -------
    mean : float
        Population-averaged LvR.
    LvR : numpy.ndarray
        Single-cell LvR values
    """
    i_min = np.searchsorted(data_array[0], t_min)
    i_max = np.searchsorted(data_array[0], t_max)
    LvR = np.array([])
    data_array = data_array[:,i_min:i_max]
    for i in np.unique(data_array[1]):
        intervals = np.diff(data_array[0, np.where(data_array[1] == i)[0]])
        if intervals.size > 1:
            val = np.sum((1. - 4 * intervals[0:-1] * intervals[1:] / (intervals[0:-1] + intervals[
                         1:]) ** 2) * (1 + 4 * t_ref / (intervals[0:-1] + intervals[1:])))
            LvR = np.append(LvR, val * 3 / (intervals.size - 1.))
        else:
            LvR = np.append(LvR, 0.0)
    if len(LvR) < num_neur:
        LvR = np.append(LvR, np.zeros(num_neur - len(LvR)))
    return np.mean(LvR), LvR

def calc_correlations(data_array, t_min, t_max, subsample=2000, resolution=1.0):
    # Get unique neuron ids
    ids = np.unique(data_array[1])
    
    # Extract spike train i.e. sorted array of spike times for each neuron
    # **NOTE** this is a version of correlation_toolbox.helper.sort_gdf_by_id, 
    # modified to suit our data format
    # +1000 to ensure that we really have subsample non-silent neurons in the end
    ids = np.arange(ids[0], ids[0]+subsample+1001)
    dat = []
    for i in ids:
        dat.append(np.sort(data_array[0, np.where(data_array[1] == i)[0]]))

    # Calculate correlation coefficient
    # **NOTE** this comes from the compute_corrcoeff.py in original paper repository
    bins, hist = ch.instantaneous_spike_count(dat, resolution, tmin=t_min, tmax=t_max)
    rates = ch.strip_binned_spiketrains(hist)[:subsample]
    cc = np.corrcoef(rates)
    cc = np.extract(1-np.eye(cc[0].size), cc)
    cc[np.where(np.isnan(cc))] = 0.
    
    # Return mean correlation coefficient
    return np.mean(cc)
    
def calc_stats(data_path, duration_s, population_name, population_sizes):
    # Get list of all data files for this population
    spike_files = list(glob(path.join(data_path, "recordings", "*_%s.npy" % population_name)))
    
    rates = np.empty(len(spike_files))
    irregularity = np.empty(len(spike_files))
    correlation = np.empty(len(spike_files))
    for i, s in enumerate(spike_files):
        # Load spike data
        data = np.load(s)
         
        # Extract population name
        name_components = path.basename(s).split("_")
        area_name = name_components[0]
        pop_name = name_components[1].split(".")[0]

        # Count neurons
        num_neurons = int(population_sizes[area_name][pop_name])

        # Count spikes that occur after first 500ms
        num_spikes = np.sum(data[0] > 500.0)
        
        # Calculate rate
        rates[i] = num_spikes / (num_neurons * (duration_s - 0.5))
    
        # Calculate irregularity
        irregularity[i] = pop_LvR(data, 2.0, 500.0, duration_s * 1000.0, num_neurons)[0]
        
        # Calculate correlation coefficient
        correlation[i] = calc_correlations(data, 500.0, duration_s * 1000.0)

    np.save("genn_rates_%s.npy" % population_name, rates)
    np.save("genn_irregularity_%s.npy" % population_name, irregularity)
    np.save("genn_corr_coeff_%s.npy" % population_name, correlation)

if __name__ == '__main__':
    assert len(argv) == 2
    data_path = argv[1]

    # Find model description
    custom_data_model_filename = list(glob(path.join(data_path, "custom_Data_Model_*.json")))
    print(custom_data_model_filename)
    #assert len(custom_data_model_filename) == 1
    custom_data_model_filename = custom_data_model_filename[0]
    print("Using custom data model %s" % custom_data_model_filename)

    # Load model description and extract population sizes
    custom_data_model = json.load(open(custom_data_model_filename, "r"))
    population_sizes = custom_data_model["neuron_numbers"]

    # Entry point
    populations = ["4E", "4I", "5E", "5I", "6E", "6I", "23E", "23I"]

    # Create processes to calculate stats for each population
    processes = [Process(target=calc_stats, args=(data_path, 100.5, p, population_sizes)) 
                 for p in populations]
     
    # Start processes
    for p in processes:
        p.start()
        
    # Join processes
    for p in processes:
        p.join()
