#!/usr/bin/env python3

# -*- coding: utf-8 -*-
# @Author: Patrick Bos
# @Date:   2016-11-16 16:23:55
# @Last Modified by:   E. G. Patrick Bos
# @Last Modified time: 2017-05-05 08:24:28

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import glob
import os
import functools
from pathlib import Path

pd.set_option("display.width", None)


def merge_dataframes(*dataframes):
    return functools.reduce(pd.merge, dataframes)


def df_from_json_incl_meta(fp, fp_meta=None,
                           drop_meta=['N_gaussians', 'N_observables',
                                      'N_parameters', 'parallel_interleave',
                                      'seed', 'force_num_int', 'print_level',
                                      'time_num_ints', 'timing_flag',
                                      'optConst'],
                           drop_nan=False):
    result = {}
    if fp_meta is None:
        fp_meta = fp.with_name('timing_meta.json')
    main_df = pd.read_json(fp)
    meta_df = pd.read_json(fp_meta).drop(drop_meta, axis=1)
    # not just single process runs, also master processes in multi-process runs:
    single_and_master_process = pd.merge(main_df, meta_df, how='left', on='pid')
    if 'ppid' in main_df.columns:
        single_and_master_process.drop('ppid', axis=1, inplace=True)
        multi_process = pd.merge(main_df, meta_df, how='left',
                                 left_on='ppid', right_on='pid').drop('pid_y', axis=1)
        multi_process.rename(columns={'pid_x': 'pid'}, inplace=True)
        result['multi'] = multi_process

    single_process = single_and_master_process[single_and_master_process.num_cpu == 1].copy()
    master_process = single_and_master_process[single_and_master_process.num_cpu > 1].copy()
    if len(single_process) > 0:
        result['single'] = single_process
    if len(master_process) > 0:
        result['master'] = master_process

    if drop_nan:
        result = {k: df.dropna() for k, df in result.items()}

    return result


def merge_dfs_by_split_per_filetype(dfdicts_by_split, split_key, filetype_keys):
    dfs_split_items = {}
    # first filter out the items of the split_key
    for fp, dfdict in dfdicts_by_split.items():
        try:
            dfs_split_items[fp] = dfdict[split_key]
        except KeyError:
            continue

    # then concatenate the dfs per filetype key
    dfs = {}
    for k in filetype_keys:
        df_merge_list = []
        for fp, df in dfs_split_items.items():
            if fp.match('*' + k + '*'):
                df_merge_list.append(df)
        try:
            dfs[k] = pd.concat(df_merge_list)
        except ValueError:
            continue

    return dfs


def savefig(factorplot, fp):
    try:
        g.savefig(fp)
        print("saved figure using pathlib.Path, apparently mpl is now pep 519 compatible! https://github.com/matplotlib/matplotlib/pull/8481")
    except TypeError:
        g.savefig(fp.__str__())


"""
cd ~/projects/apcocsm/code/profiling/numIntSet_timing
rsync -avr nikhef:project_atlas/apcocsm_code/profiling/numIntSet_timing/unbinned_scaling2 ./
"""

basepath = Path.home() / 'projects/apcocsm/code/profiling/numIntSet_timing/unbinned_scaling2'
savefig_dn = basepath / 'analysis'

#### LOAD DATA FROM FILES
fplist = [fp for fp in basepath.glob('18311*.allier.nikhef.nl/*.json')
          if not fp.match('timing_meta.json')]

uniquefps = list(set(fp.name for fp in fplist))
dfkeys = [u[u.find('_') + 1:u.rfind('.')] for u in uniquefps]

# "split" by single, multi and master and of course by file still
dfs_split = {fp: df_from_json_incl_meta(fp) for fp in fplist}
dfs_sp = merge_dfs_by_split_per_filetype(dfs_split, 'single', dfkeys)
dfs_mp_sl = merge_dfs_by_split_per_filetype(dfs_split, 'multi', dfkeys)
dfs_mp_ma = merge_dfs_by_split_per_filetype(dfs_split, 'master', dfkeys)


#### TOTAL TIMINGS
df_totals = pd.concat([dfs_sp['full_minimize'], dfs_mp_ma['full_minimize']])

### ADD IDEAL TIMING BASED ON SINGLE CORE RUNS
single_core = df_totals[df_totals.num_cpu == 1]

# estimate ideal curve from fastest single_core run:
single_core_fastest = single_core.groupby('N_events', as_index=False).min()
df_ideal = single_core_fastest.copy()
for num_cpu in df_totals.num_cpu.unique():
    if num_cpu != 1:
        ideal_num_cpu_i = single_core_fastest.copy()
        ideal_num_cpu_i.full_minimize_wall_s /= num_cpu
        ideal_num_cpu_i.num_cpu = num_cpu
        df_ideal = df_ideal.append(ideal_num_cpu_i)

df_totals['timing_type'] = pd.Series(len(df_totals) * ('real',), index=df_totals.index)
df_ideal['timing_type'] = pd.Series(len(df_ideal) * ('ideal',), index=df_ideal.index)

df_totals = df_totals.append(df_ideal)

# add combination of two categories
df_totals['N_events/timing_type'] = df_totals.N_events.astype(str) + '/' + df_totals.timing_type.astype(str)


#### NUMERICAL INTEGRAL TIMINGS
df_numints = dfs_mp_sl['numInts'].copy()

# add iteration information, which can be deduced from the order, ppid, num_cpu and name (because u0_int is only done once, we have to add a special check for that)
numints_iteration = []
it = 0
N_names = len(df_numints.name.unique())
# local_N_num_int is the number of numerical integrals in the local (current) iteration
# it determines after how long the next iteration starts
local_N_num_int = df_numints.num_cpu.iloc[0] * N_names
# the current iteration starts here:
current_iteration_start = 0
current_ppid = df_numints.ppid.iloc[0]
for irow, row in enumerate(df_numints.itertuples()):
    if ((irow - current_iteration_start) == local_N_num_int) or current_ppid != row.ppid:
        current_ppid = row.ppid
        current_iteration_start = irow
        it += 1
        local_N_names = len(df_numints[irow:irow + N_names * row.num_cpu].name.unique())
        local_N_num_int = row.num_cpu * local_N_names

    numints_iteration.append(it)

    # if (irow + 1) % local_N_num_int == 0:
    #     it += 1

df_numints['iteration'] = numints_iteration

df_numints_min_by_iteration = df_numints.groupby('iteration').min()
df_numints_max_by_iteration = df_numints.groupby('iteration').max()

#### ANALYSIS

# full timings
g = sns.factorplot(x='num_cpu', y='full_minimize_wall_s', col='N_events', hue='N_events/timing_type', estimator=np.min, data=df_totals, legend_out=False, sharey=False)
plt.subplots_adjust(top=0.85)
g.fig.suptitle('total wallclock timing of minimize("Minuit2", "migrad")')
savefig(g, savefig_dn / 'total_timing.png')

# numerical integrals

# g = sns.factorplot(x='num_cpu', y='wall_s', col='N_events', sharey='row', estimator=np.sum, data=df_numints, legend_out=False)
# plt.subplots_adjust(top=0.85)
# g.fig.suptitle('sum over CPUs of wallclock timings of all timed numerical integrals')
# savefig(g, savefig_dn / 'numInts_sum.png')

g = sns.factorplot(x='num_cpu', y='wall_s', col='N_events', sharey='row', estimator=np.min, data=df_numints, legend_out=False)
plt.subplots_adjust(top=0.85)
g.fig.suptitle('wallclock timing of all timed numerical integrals --- minima of all integrations per plotted factor --- vertical bars: variation in different runs and iterations')
savefig(g, savefig_dn / 'numInts_min.png')

g = sns.factorplot(x='num_cpu', y='wall_s', col='N_events', sharey='row', estimator=np.max, data=df_numints, legend_out=False)
plt.subplots_adjust(top=0.85)
g.fig.suptitle('wallclock timing of all timed numerical integrals --- maxima of all integrations per plotted factor --- vertical bars: variation in different runs and iterations')
savefig(g, savefig_dn / 'numInts_max.png')


# g = sns.factorplot(x='num_cpu', y='wall_s', col='N_events', sharey='row', estimator=np.sum, data=df_numints_min_by_iteration, legend_out=False)
# plt.subplots_adjust(top=0.85)
# g.fig.suptitle('sum over CPUs and iterations of minimum wallclock timing per iteration of all timed numerical integrals')
# savefig(g, savefig_dn / 'numInts_it_min_sum.png')

g = sns.factorplot(x='num_cpu', y='wall_s', col='N_events', sharey='row', estimator=np.sum, data=df_numints_max_by_iteration, legend_out=False)
plt.subplots_adjust(top=0.8)
g.fig.suptitle('wallclock timing of all timed numerical integrals --- sum of maximum of each iteration per run $\sum_{\mathrm{it}} \max_{\mathrm{core}}(t_{\mathrm{run,it,core}})$ --- vertical bars: variation in different runs')
savefig(g, savefig_dn / 'numInts_it_sum_max.png')

# plt.show()
