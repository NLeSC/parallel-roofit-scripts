#!/usr/bin/env bash
# @Author: Patrick Bos
# @Date:   2016-11-16 16:54:41
# @Last Modified by:   E. G. Patrick Bos
# @Last Modified time: 2017-07-31 07:01:56

#PBS -l nodes=1:ppn=8
#PBS -o $PBS_JOBNAME/$PBS_JOBID.out
#PBS -e $PBS_JOBNAME/$PBS_JOBID.err

if [[ "$bunch" == true && -z "$argument_string_bunch_file" ]]; then
  echo "Error: in bunch mode, but argument_string_bunch_file environment variable not set!"
  exit 1
fi

#set -e
# Any subsequent(*) commands which fail will cause the shell script to exit immediately
# DON'T USE SET -E TOGETHER WITH EXPAND_ALIASES!
shopt -s expand_aliases
# ALIASES MOETEN AANGEZET WORDEN (http://unix.stackexchange.com/a/1498/193258)

source $HOME/root_run_deps.sh

export SCRIPT_PATH="$HOME/project_atlas/apcocsm_code/workbench.cpp"

export BASERUNDIR="$HOME/project_atlas/apcocsm_code/profiling/workbench"
export RUNDIR="$BASERUNDIR/$PBS_JOBNAME/$PBS_JOBID"

# go to run-dir
mkdir -p $RUNDIR
cd $RUNDIR

function start_run() {
  if [[ -z "$run_id" || -z "$timing_flag" || -z "$workspace_filepath" || -z "$workspace_name" || -z "$ileave" || -z "$seed" || -z "$printlevel" || -z "$optConst" || -z "$time_num_ints" || -z "$num_cpu" || -z "$fork_timer" || -z "$fork_timer_sleep_us" || -z "$cpu_affinity" || -z "$debug" || -z "$total_cpu_timing" || -z "$fix_binned_pdfs" || -z "$zero_initial_POI" || -z "$time_evaluate_partition" || -z "$time_MPFE_forks" ]]; then
    echo "Error: configuration environment variable missing!"
    echo "run_id: $run_id"
    echo "workspace_filepath: $workspace_filepath"
    echo "workspace_name: $workspace_name"
    echo "num_cpu: $num_cpu"
    echo "optConst: $optConst"
    echo "ileave: $ileave"
    echo "cpu_affinity: $cpu_affinity"
    echo "seed: $seed"
    echo "timing_flag: $timing_flag"
    echo "time_num_ints: $time_num_ints"
    echo "fork_timer: $fork_timer"
    echo "fork_timer_sleep_us: $fork_timer_sleep_us"
    echo "printlevel: $printlevel"
    echo "debug: $debug"
    echo "total_cpu_timing: $total_cpu_timing"
    echo "fix_binned_pdfs: $fix_binned_pdfs"
    echo "zero_initial_POI: $zero_initial_POI"
    echo "time_evaluate_partition: $time_evaluate_partition"
    echo "time_MPFE_forks: $time_MPFE_forks"
    exit 1
  fi

  if [[ -z "$model_config" || -z "$data_name" || -z "$POI_name" ]]; then
    echo "Warning: string configuration environment variable empty! This may not be intended."
    echo "model_config: $model_config"
    echo "data_name: $data_name"
    echo "POI_name: $POI_name"
  fi

  if [[ -z "$repeat_nr" ]]; then
    echo "repeat_nr not set as environment variable"
  else
    echo "Repeat number $repeat_nr"
  fi

  root -b -q -l "$SCRIPT_PATH(\"${workspace_filepath}\",\"${workspace_name}\",\"${model_config}\",\"${data_name}\",${num_cpu},${optConst},${ileave},${cpu_affinity},${seed},${timing_flag},${time_num_ints},${fork_timer},${fork_timer_sleep_us},${printlevel},${debug},${total_cpu_timing},${fix_binned_pdfs},${zero_initial_POI},\"${POI_name}\",${time_evaluate_partition},${time_MPFE_forks})"

  cd -
}

if [[ "$bunch" == false ]]; then
  start_run
else
  echo "starting runs in bunch mode"
  bunch_i=1
  while IFS= read -r argument_string ; do
    echo "bunch ${bunch_i}"
    eval $argument_string
    start_run
    bunch_i=$((bunch_i+1))
  done < "${BASERUNDIR}/${argument_string_bunch_file}"
fi
