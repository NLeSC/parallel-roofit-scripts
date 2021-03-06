# -*- coding: utf-8 -*-
# @Author: patrick
# @Date:   2016-09-01 17:04:53
# @Last Modified by:   Patrick Bos
# @Last Modified time: 2016-10-26 14:48:09

# as per tensorflow styleguide
# https://www.tensorflow.org/versions/r0.11/how_tos/style_guide.html
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from tensorflow.python.platform import tf_logging as logging
import numpy as np
import matplotlib.pyplot as plt
from timeit import default_timer as timer
import time
import os

tf.logging.set_verbosity(tf.logging.INFO)


project_dn = os.path.expanduser("~/projects/apcocsm/")
# project_dn = "/home/pbos/apcocsm/"

m0_num = 5.291
argpar_num = -20.0

constraint = {}

constraint['sigmean'] = (5.20, 5.30)
constraint['sigwidth'] = (0.001, 1.)
constraint['argpar'] = (-100., -1.)
constraint['nsig'] = (0., 10000)
constraint['nbkg'] = (0., 10000)
constraint['mes'] = (5.20, 5.30)

# keep a variable dictionary for easy key-based access compatible with constraints
vdict = {}


pi = tf.constant(np.pi, dtype=tf.float64, name="pi")
sqrt2pi = tf.constant(np.sqrt(2 * np.pi), dtype=tf.float64, name="sqrt2pi")
two = tf.constant(2, dtype=tf.float64, name="two")
one = tf.constant(1, dtype=tf.float64, name="one")
zero = tf.constant(0, dtype=tf.float64, name="zero")


def gradsafe_sqrt(x, clip_low=1e-18, name=None):
    with tf.name_scope(name, "gradsafe_sqrt"):
        return tf.sqrt(tf.clip_by_value(x, clip_low, x))


def argus_integral_phalf(m_low, m_high, m0, c):
    """
    Only valid for argus_pdf with p=0.5! Otherwise need to do numerical
    integral.
    """
    def F(m_bound, name=None):
        with tf.name_scope(name, "argus_integral_phalf_primitive"):
            a = tf.minimum(m_bound, m0)
            x = 1 - tf.pow(a / m0, 2)
            primitive = -0.5 * m0 * m0 * (tf.exp(c * x) * tf.sqrt(x) / c + 0.5 / tf.pow(-c, 1.5) * tf.sqrt(pi) * tf.erf(gradsafe_sqrt(-c * x)))
            # We have to safeguard the sqrt, because otherwise the analytic
            # derivative blows up for x = 0
            return primitive

    area = tf.sub(F(m_high, name="F2"), F(m_low, name="F1"), name="argus_integral_phalf")
    return area


def argus_pdf_phalf_WN(m, m0, c, m_low, m_high):
    """
    WN: with normalization
    """
    norm = argus_integral_phalf(m_low, m_high, m0, c)
    return argus_pdf(m, m0, c) / norm


# // --- Observable ---
# RooRealVar mes("mes","m_{ES} (GeV)",5.20,5.30) ;

# // --- Build Gaussian signal PDF ---
# RooRealVar sigmean("sigmean","B^{#pm} mass",5.28,5.20,5.30) ;
# RooRealVar sigwidth("sigwidth","B^{#pm} width",0.0027,0.001,1.) ;

sigmean = tf.Variable(5.28, name="sigmean", dtype=tf.float64)
sigwidth = tf.Variable(0.0027, name="sigwidth", dtype=tf.float64)
vdict['sigmean'] = sigmean
vdict['sigwidth'] = sigwidth

# RooGaussian gauss("gauss","gaussian PDF",mes,sigmean,sigwidth) ;


def gaussian_pdf(x, mean, std):
    val = tf.div(tf.exp(-tf.pow((x - mean) / std, 2) / two), (sqrt2pi * std),
                 name="gaussian_pdf")
    return val


# // --- Build Argus background PDF ---
# RooRealVar argpar("argpar","argus shape parameter",-20.0,-100.,-1.) ;
# RooConstVar m0("m0", "resonant mass", 5.291);

argpar = tf.Variable(argpar_num, name="argpar", dtype=tf.float64)
m0 = tf.constant(m0_num, name="m0", dtype=tf.float64)
vdict['argpar'] = argpar

# RooArgusBG argus("argus","Argus PDF",mes,m0,argpar) ;


def argus_pdf(m, m0, c, p=0.5):
    t = m / m0
    u = 1 - t * t
    argus_t_ge_1 = m * tf.pow(u, p) * tf.exp(c * u)
    return tf.maximum(tf.zeros_like(m), argus_t_ge_1, name="argus_pdf")


# // --- Construct signal+background PDF ---
# RooRealVar nsig("nsig","#signal events",200,0.,10000) ;
# RooRealVar nbkg("nbkg","#background events",800,0.,10000) ;

nsig = tf.Variable(200, name="nsig", dtype=tf.float64)
nbkg = tf.Variable(800, name="nbkg", dtype=tf.float64)
vdict['nsig'] = nsig
vdict['nbkg'] = nbkg

# RooAddPdf sum("sum","g+a",RooArgList(gauss,argus),RooArgList(nsig,nbkg)) ;

# // --- Generate a toyMC sample from composite PDF ---
# RooDataSet *data = sum.generate(mes,2000) ;


def sum_pdf(mes, nsig, sigmean, sigwidth, nbkg, m0, argpar, mes_low, mes_high):
    add = tf.add(nsig * gaussian_pdf(mes, sigmean, sigwidth),
                 nbkg * argus_pdf_phalf_WN(mes, m0, argpar, mes_low, mes_high),
                 name="sum_pdf")
    return tf.div(add, nsig + nbkg, name="sum_pdf_normalized")


# data in RooFit genereren en importeren
# draai dit in ROOT:
# data.write("roofit_demo_random_data_values.dat");
# om het weer in te lezen:
# RooDataSet *data;
# data->RooDataSet.read("roofit_demo_random_data_values.dat", RooArgList(mes))
data_raw = np.loadtxt(project_dn + "roofit_demo_random_data_values.dat",
                      dtype=np.float64)
data = tf.constant(data_raw, name='event_data', dtype=tf.float64)

# // --- Perform extended ML fit of composite PDF to toy data ---
# sum.fitTo(*data,"Extended") ;

# convert to tf constants, otherwise you'll get complaints about float32s...
constraint_tf = {}
for key in constraint.keys():
    low = constraint[key][0]
    high = constraint[key][1]
    constraint_tf[key] = (tf.constant(low, dtype=tf.float64),
                          tf.constant(high, dtype=tf.float64))


print("N.B.: using direct data entry")
likelihood = sum_pdf(data, nsig, sigmean, sigwidth, nbkg, m0, argpar, constraint_tf['mes'][0], constraint_tf['mes'][1])
nll = tf.neg(tf.reduce_sum(tf.log(likelihood)), name="nll")


variables = tf.all_variables()

grads = tf.gradients(nll, variables)

# ### build constraint inequalities
inequalities = []
for key, (lower, upper) in constraint_tf.iteritems():
    if key != 'mes':
        inequalities.append(vdict[key] - lower)
        inequalities.append(upper - vdict[key])

# ### build bounds instead of inequalities (only for L-BFGS-B, TNC and SLSQP)
# N.B.: order important! Also supply variables to be sure the orders match.
bounds = []
for v in variables:
    key = v.name[:v.name.find(':')]
    lower, upper = constraint[key]
    bounds.append((lower, upper))


max_steps = 1000
status_every = 1


# Create an optimizer with the desired parameters.
opt = tf.contrib.opt.ScipyOptimizerInterface(nll,
                                             options={'maxiter': max_steps,
                                                      # 'disp': True,
                                                      # 'tol': 1e-20,
                                                      'maxls': 10,
                                                      },
                                             # inequalities=inequalities,
                                             # method='SLSQP'  # supports inequalities
                                             # method='BFGS',
                                             bounds=bounds,
                                             var_list=variables,  # supply with bounds to match order!
                                             tol=1e-14,
                                             )

tf.scalar_summary('nll', nll)

init_op = tf.initialize_all_variables()

# from http://stackoverflow.com/a/35907755/1199693
config = tf.ConfigProto(graph_options=tf.GraphOptions(
    # optimizer_options=tf.OptimizerOptions(opt_level=tf.OptimizerOptions.L2))) # L2 werkt niet (wrs eruit gehaald)
    optimizer_options=tf.OptimizerOptions(opt_level=tf.OptimizerOptions.L1)))

# start session
with tf.Session(config=config) as sess:
    # Merge all the summaries and write them out to /tmp/mnist_logs (by default)
    summarize_merged = tf.merge_all_summaries()
    summary_writer = tf.train.SummaryWriter('./train/%i' % int(time.time()), sess.graph)
    # Run the init operation.
    sess.run(init_op)

    true_vars = {}
    for v in variables:
        key = v.name[:v.name.find(':')]
        true_vars[key] = v.eval()

    true_vars['m0'] = m0.eval()

    print("name\t" + "\t".join([v.name.ljust(10) for v in variables]) + "\t | <nll>\t\t | step")
    print("init\t" + "\t".join(["%6.4e" % v for v in sess.run(variables)]) + "\t | %f" % np.mean(sess.run(nll)))
    print("")

    step = 0

    nll_value_opt = sess.run(nll)

    def step_callback(var_values_opt):
        global step, sess, summary_writer, nll_value_opt

        summary = sess.run(summarize_merged)
        summary_writer.add_summary(summary, step)
        if step % status_every == 0:
            print("opt\t" + "\t".join(["%6.4e" % v for v in var_values_opt]) + "\t | %f\t | %i" % (np.mean(nll_value_opt), step))

        step += 1

    def loss_callback(nll_value_opt_step, g1, g2, g3, g4, g5, *other_vars):
        global nll_value_opt
        nll_value_opt = nll_value_opt_step
        print("loss_callback:")
        print("nll:", nll_value_opt)
        print("gradients:", g1, g2, g3, g4, g5)
        ov = "\t".join([str(v) for v in other_vars])
        if ov:
            print("variables:", ov)
        print("")

    """
    start = timer()

    opt.minimize(session=sess, step_callback=step_callback,
                 loss_callback=loss_callback, fetches=[nll] + grads + variables)
    # N.B.: callbacks not supported with SLSQP!

    end = timer()

    print("Loop took %f seconds" % (end - start))

    """
    N_loops = 100
    timings = []
    tf.logging.set_verbosity(tf.logging.ERROR)

    for i in range(N_loops):
        sess.run(init_op)
        start = timer()
        opt.minimize(session=sess)
        end = timer()
        timings.append(end - start)

    tf.logging.set_verbosity(tf.logging.INFO)

    print("Timing total: %f s, average: %f s, minimum: %f s" % (np.sum(timings), np.mean(timings), np.min(timings)))

    # logging.info("get fitted variables")
    fit_vars = {}
    for v in variables:
        key = v.name[:v.name.find(':')]
        fit_vars[key] = v.eval()

    fit_vars['m0'] = m0.eval()

    print("fit \t" + "\t".join(["%6.4e" % v for v in sess.run(variables)]) + "\t | %f" % np.mean(sess.run(nll)))

    root_fit_vals = {'argpar': -22.8765, 'nbkg': 816.137, 'nsig': 195.976,
                     'sigmean': 5.27987, 'sigwidth': 3.01048e-3, 'nll': -4976.4}

    print("=== WARNING: setting variables to ROOT fit values! ===")
    for v in variables:
        key = v.name[:v.name.find(':')]
        sess.run(v.assign(root_fit_vals[key]))

    nll_root_val = sess.run(nll)

    print("ROOT \t" + "\t".join(["%6.4e" % root_fit_vals[v.name[:v.name.find(':')]] for v in variables]) + "\t | %f (own calc: %f)" % (root_fit_vals['nll'], nll_root_val))

    # FCN=-4976.4 FROM MIGRAD    STATUS=CONVERGED     101 CALLS         102 TOTAL
    #                     EDM=1.00861e-05    STRATEGY= 1      ERROR MATRIX ACCURATE 
    #  EXT PARAMETER                                   STEP         FIRST   
    #  NO.   NAME      VALUE            ERROR          SIZE      DERIVATIVE 
    #   1  argpar      -2.28765e+01   3.42616e+00   3.56317e-03  -1.23184e-02
    #   2  nbkg         8.16137e+02   9.44657e+02   1.04092e-03   7.76879e-02
    #   3  nsig         1.95976e+02   2.30582e+02   4.93414e-04  -1.64158e-01
    #   4  sigmean      5.27987e+00   2.15796e-04   2.61026e-04  -3.20933e-01
    #   5  sigwidth     3.01048e-03   1.99232e-04   1.93308e-04   5.48995e-01

    # // --- Plot toy data and composite PDF overlaid ---
    # RooPlot* mesframe = mes.frame() ;
    # data->plotOn(mesframe) ;
    # sum.plotOn(mesframe) ;
    # sum.plotOn(mesframe,Components(argus),LineStyle(kDashed)) ;
    # mesframe->Draw();

    # logging.info("create data histogram")
    counts, bins = np.histogram(data.eval(), bins=100)
    x_bins = (bins[:-1] + bins[1:]) / 2

    # logging.info("evaluate pdf values")
    y_fit = sum_pdf(x_bins, mes_low=constraint_tf['mes'][0], mes_high=constraint_tf['mes'][1], **fit_vars).eval()
    argus_fit = argus_pdf_phalf_WN(x_bins, fit_vars['m0'], fit_vars['argpar'], m_low=constraint_tf['mes'][0], m_high=constraint_tf['mes'][1]).eval()

    y_true = sum_pdf(x_bins, mes_low=constraint_tf['mes'][0], mes_high=constraint_tf['mes'][1], **true_vars).eval()

    # normalize fit values to data counts
    y_fit_norm = np.sum(counts) / np.sum(y_fit)
    y_fit = [y * y_fit_norm for y in y_fit]

    argus_fit_norm = fit_vars['nbkg'] / (fit_vars['nsig'] + fit_vars['nbkg'])
    argus_fit = [a * argus_fit_norm * y_fit_norm for a in argus_fit]

    y_true_norm = np.sum(counts) / np.sum(y_true)
    y_true = [y * y_true_norm for y in y_true]

    # plot results
    # plt.errorbar(x_bins, counts, yerr=np.sqrt(counts), fmt='.g', label="input data")
    # plt.plot(x_bins, y_fit, '-b', label="fit sum_pdf")
    # plt.plot(x_bins, argus_fit, '--b', label="fit argus_pdf")
    # plt.plot(x_bins, y_true, ':k', label="true sum_pdf")
    # plt.legend(loc='best')

    # plt.show()
