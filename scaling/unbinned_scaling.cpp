#include <chrono>
#include <iostream>
#include <sstream>
#include <fstream>
#include <string>

using namespace RooFit;

// call from command line like, for instance:
// root -l 'unbinned_scaling.cpp(20,5,8,1000)'

// timing_flag is used to activate only selected timing statements [1-7]

void unbinned_scaling(int N_gaussians, int N_observables, int N_parameters,
                      int N_events, int num_cpu, int parallel_interleave,
                      int seed, int print_level=0, int timing_flag=1) {
  //gSystem->Exec("top -n1 -b");
  // num_cpu: -1 is special option -> overhead communicatie protocol vergelijken (vgl met 1 cpu)
  // parallel_interleave: 0 = blokken gelijke grootte, 1 = interleave
  //                      
  //             binned:         generateBinned ipv generate -> als je aantal events ongeveer even groot is als aantal bins krijg je load balancing problemen, dat zou interleave beetje moeten ondervangen
  // verwachtingen
  // - historisch: tot ~8 cpu gaat het goed
  // - weinig data en veel parameters: comm overhead belangrijk (fit snel, veel tijd in oversturen params)
  // - weinig parameters, veel data: scalability hoort beter te zijn (minder comm overhead) -> bottom line van wat de software kan
  // - observables even op 1 houden, alles optellen klopt conceptueel-statistisch niet

  // scaling configuration
  // int N_gaussians(20);
  // int N_observables(5);
  // int N_parameters(8);  // must be even, means and sigmas have diff ranges
  // int N_events(1000);
  ofstream outfile;

  if (timing_flag > 0) {
    outfile.open("timing_meta.json", ios::app);

    outfile << "{\"N_gaussians\": \"" << N_gaussians
            << "\", \"N_observables\": \"" << N_observables
            << "\", \"N_parameters\": \"" << N_parameters
            << "\", \"N_events\": \"" << N_events
            << "\", \"num_cpu\": \"" << num_cpu
            << "\", \"parallel_interleave\": \"" << parallel_interleave
            << "\", \"seed\": \"" << seed
            << "\", \"pid\": \"" << getpid()
            << "\"}," << std::endl;

    outfile.close();
  }

  // RooConstVar roo_timing_flag("timing_flag", "timing_flag", timing_flag);
  // gROOT->GetListOfSpecials()->Add(&roo_timing_flag);

  RooTrace::timing_flag = timing_flag;

  // plotting configuration
  int obs_plot_x(3);
  int obs_plot_y(2);
  int obs_plot_x_px(1200);
  int obs_plot_y_px(800);

  // other stuff
  int printlevel(print_level);
  int optimizeConst(2);
  // int N_timing_loops(3); // not used

  gRandom->SetSeed(seed);

  // some sanity checks
  if (obs_plot_x * obs_plot_y < N_observables) {
    std::cout << "WARNING: obs_plot_x * obs_plot_y < N_observables,"
                 " won't be able to plot all observables!"
              << std::endl << std::endl;
  }
  if (N_parameters % 2 != 0) {
    std::cout << "set N_parameters to an even number!" << std::endl;
    exit(2);
  }

  // here we go!

  RooWorkspace w("w", 1) ;

  RooArgSet obs_set;

  // create gaussian parameters
  float mean[N_parameters/2], sigma[N_parameters/2];
  for (int ix = 0; ix < N_parameters/2; ++ix) {
    mean[ix] = gRandom->Gaus(0, 2);
    sigma[ix] = 0.1 + abs(gRandom->Gaus(0, 2));
  }

  // create gaussians and also the observables and parameters they depend on
  for (int ix = 0; ix < N_gaussians; ++ix) {
    std::cout << ix << std::endl;
    std::ostringstream os;
    // int ix_p = (ix/2) % N_parameters;
    int ix_p = ix % (N_parameters / 2);
    os << "Gaussian::g" << ix
       << "(x" << ix % N_observables << "[-10,10],"
       << "m" << ix_p << "[" << mean[ix_p] << ",-10,10],"
       << "s" << ix_p << "[" << sigma[ix_p] << ",0.1,10])";
    std::string s = os.str();
    w.factory(s.c_str());
  }

  // create uniform background signals on each observable
  for (int ix = 0; ix < N_observables; ++ix) {
    {
      std::ostringstream os;
      os << "Uniform::u" << ix << "(x" << ix << ")";
      std::string s = os.str();
      w.factory(s.c_str());
    }

    // gather the observables in a list for data generation below
    {
      std::ostringstream os;
      os << "x" << ix;
      std::string s = os.str();
      obs_set.add(*w.arg(s.c_str()));
    }
  }

  RooArgSet pdf_set = w.allPdfs();

  // create event counts for all pdfs
  RooArgSet count_set;

  // ... for the gaussians
  for (int ix = 0; ix < N_gaussians; ++ix) {
    std::stringstream os, os2;
    os << "Nsig" << ix;
    std::string s = os.str();
    os2 << "#signal events comp " << ix;
    std::string s2 = os2.str();
    RooRealVar a(s.c_str(), s2.c_str(), 100, 0., 10*N_events);
    w.import(a);
  }
  // gather them in count_set
  for (int ix = 0; ix < N_gaussians; ++ix) {
    std::stringstream os;
    os << "Nsig" << ix;
    std::string s = os.str();
    count_set.add(*w.arg(s.c_str()));
  }
  // ... and for the uniform background components
  for (int ix = 0; ix < N_observables; ++ix) {
    std::stringstream os, os2;
    os << "Nbkg" << ix;
    std::string s = os.str();
    os2 << "#background events comp " << ix;
    std::string s2 = os2.str();
    RooRealVar a(s.c_str(), s2.c_str(), 100, 0., 10*N_events);
    w.import(a);
  }
  // gather them in count_set
  for (int ix = 0; ix < N_observables; ++ix) {
    std::stringstream os;
    os << "Nbkg" << ix;
    std::string s = os.str();
    count_set.add(*w.arg(s.c_str()));
  }

  RooAddPdf sum("sum", "gaussians+uniforms", pdf_set, count_set);

  // --- Generate a toyMC sample from composite PDF ---
  RooDataSet *data = sum.generate(obs_set, N_events);
/*
  // OR reload previously written out sample:
  // wegschrijven:
  data.write("roofit_demo_random_data_values.dat");
  // om het weer in te lezen:
  RooDataSet *data = RooDataSet::read("../roofit_demo_random_data_values.dat", RooArgList(mes));
*/


  // --- Perform extended ML fit of composite PDF to toy data ---
  // sum.fitTo(*data,"Extended") ;
  // instead of full fitTo, only do the fit, leave out error matrix, using
  // run style of run_higgs.C
  std::chrono::time_point<std::chrono::high_resolution_clock> begin, end;

  if (timing_flag == 1) {
    outfile.open("timing_full_minimize.json", ios::app);
  }

  // for (int it = 0; it < N_timing_loops; ++it)
  {
    RooAbsReal* nll = sum.createNLL(*data, NumCPU(num_cpu, parallel_interleave));//, "Extended");
    RooMinimizer m(*nll);
    // m.setVerbose(1);
    m.setStrategy(0);
    m.setProfile(1);
    m.setPrintLevel(printlevel);
    m.optimizeConst(optimizeConst);

    if (timing_flag == 1) {
      begin = std::chrono::high_resolution_clock::now();
    }
    // m.hesse();

    m.minimize("Minuit2", "migrad");

    if (timing_flag == 1) {
      end = std::chrono::high_resolution_clock::now();

      float timing_s = std::chrono::duration_cast<std::chrono::nanoseconds>
                       (end-begin).count() / static_cast<float>(1e9);
      std::cout << timing_s << "s" << std::endl;

      outfile << "{\"full_minimize_wall_s\": \"" << timing_s
              << "\", \"pid\": \"" << getpid()
              << "\"}," << std::endl;
    }
  }
  if (timing_flag == 1) {
    outfile.close();
  }

  // print the "true" values for comparison
  std::cout << "--- values of PDF parameters used for data generation:"
            << std::endl;
  for (int ix = 0; ix < N_parameters/2; ++ix) {
    std::cout << "    gauss " << ix << ": m = " << mean[ix] << ", s = "
              << sigma[ix] << std::endl;
  }

  // --- Plot toy data and composite PDF overlaid ---
  TCanvas* c = new TCanvas("unbinned_scaling", "unbinned_scaling",
                           obs_plot_x_px, obs_plot_y_px);
  c->Divide(obs_plot_x, obs_plot_y);
  for (int ix = 0; ix < N_observables && ix < obs_plot_x * obs_plot_y; ++ix) {
    std::ostringstream os;
    os << "x" << ix;
    std::string s = os.str();
    RooPlot* frame = w.var(s.c_str())->frame();
    data->plotOn(frame);
    sum.plotOn(frame);
    c->cd(ix+1);
    frame->Draw();
  }
}
