#!/usr/bin/env python
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
###############################################################################
# ifm_sentinel.py -  
#
# Project:  ADP INSAR
# Purpose:  Script for processing a pair of Sentinel-1 granules with Gamma
#          
# Author:  Tom Logan
#
###############################################################################
# Copyright (c) 2018, Alaska Satellite Facility
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
# 
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.
###############################################################################

#####################
#
# Import all needed modules right away
#
#####################

import logging
import argparse
import os, re
import datetime
import time
import glob
import shutil
from lxml import etree
from interf_pwr_s1_lt_tops_proc import interf_pwr_s1_lt_tops_proc
from par_s1_slc import par_s1_slc
from SLC_copy_S1_fullSW import SLC_copy_S1_fullSW
from unwrapping_geocoding import unwrapping_geocoding
from execute import execute
from getDemFileGamma import getDemFileGamma
from makeAsfBrowse import makeAsfBrowse
from create_metadata_insar_gamma import create_readme_file

global lasttime
global log
global proc_log

def process_log(msg):
    global proc_log
    time =  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
    proc_log.write("{} - {}\n".format(time,msg))

def getBursts(mydir,name):
    back = os.getcwd()
    os.chdir(os.path.join(mydir,"annotation"))
    time = []
    for myfile in os.listdir("."):
        if name in myfile:
            root = etree.parse(myfile)
            for coord in root.iter('azimuthAnxTime'):
                time.append(float(coord.text))
            for count in root.iter('burstList'):
                total_bursts=int(count.attrib['count'])
    os.chdir(back) 
    return time,total_bursts

def getSelectBursts(masterDir,slaveDir,time):
    logging.info("Finding selected bursts at times {}, {}, {} for length {}".format(time[0],time[1],time[2],time[3]))
    burst_tab1 = "%s_burst_tab" % masterDir[17:25]
    back = os.getcwd()
    f1 = open(burst_tab1,"w")
    burst_tab2 = "%s_burst_tab" % slaveDir[17:25]
    f2 = open(burst_tab2,"w")    
    size = float(time[3])
    xml_cnt = 0
    for name in ['001.xml','002.xml','003.xml']:
        time1,total_bursts1 = getBursts(masterDir,name)
        time2,total_bursts2 = getBursts(slaveDir,name)
        cnt = 1
        found1 = 0
        for x in time1:
            if (abs(float(x)-float(time[xml_cnt])) < 0.20):
                logging.info("Found selected burst at {}".format(cnt))
                found1 = 1
                start1 = cnt
            cnt = cnt + 1
        cnt = 1
        found2 = 0
        for x in time2:
            if (abs(float(x)-float(time[xml_cnt])) < 0.20):
                logging.info("Found selected burst at {}".format(cnt))
                found2 = 1
                start2 = cnt
            cnt = cnt + 1
      
        if not found1 or not found2:
            logging.error("ERROR: Unable to find bursts at selected time")
            exit(1)

        f1.write("%s %s\n" % (start1, start1+size-1))
        f2.write("%s %s\n" % (start2, start2+size-1))
        
        xml_cnt += 1
        
    f1.close()
    f2.close()
    return(burst_tab1,burst_tab2)

def getBurstOverlaps(masterDir,slaveDir):
    logging.info("Calculating burst overlaps; in directory {}".format(os.getcwd()))
    burst_tab1 = "%s_burst_tab" % masterDir[17:25]
    back = os.getcwd()
    f1 = open(burst_tab1,"w")
    burst_tab2 = "%s_burst_tab" % slaveDir[17:25]
    f2 = open(burst_tab2,"w")    
    for name in ['001.xml','002.xml','003.xml']:
        time1,total_bursts1 = getBursts(masterDir,name)
        logging.info("total_bursts1, time1 {} {}".format(total_bursts1,time1))
        time2,total_bursts2 = getBursts(slaveDir,name)
        logging.info("total_bursts2, time2 {} {}".format(total_bursts2,time2))
        cnt = 1
        found = 0
        x = time1[0]
        for y in time2:
            if (abs(x-y) < 0.20):
                logging.info("Found burst match at 1 %s" % cnt)
                found = 1
                start1 = 1
                start2 = cnt
            cnt += 1

        if found == 0:
            y = time2[0]
            cnt = 1
            for x in time1:
                if (abs(x-y) < 0.20):
                    logging.info("Found burst match at %s 1" % cnt)
                    found = 1
                    start1 = cnt
                    start2 = 1
                cnt += 1
        
        try: 
            size1 = total_bursts1 - start1 + 1
            size2 = total_bursts2 - start2 + 1
        except:
            logging.error("ERROR: Unable to find burst overlap")
            exit(2)

        if (size1 > size2):
            size = size2
        else:
            size = size1
        
        f1.write("%s %s\n" % (start1, start1+size-1))
        f2.write("%s %s\n" % (start2, start2+size-1))
        
    f1.close()
    f2.close()
    return(burst_tab1,burst_tab2)

def getFileType(myfile):
    if "SDV" in myfile:
        type = "SDV"
        pol = "vv"
    elif "SDH" in myfile:
        type = "SDH"
        pol = "hh"
    elif "SSV" in myfile:
        type = "SSV"
        pol = "vv"
    elif "SSH" in myfile:
        type = "SSH"
        pol = "hh"
    return(type,pol)

def makeHDF5List(master,slave,outdir,output,dem_source,logname):
    gamma_version = "99.99.99"
    f = open("hdf5.txt","w")
    f.write("[Gamma DInSar]\n")
    f.write("granule = s1_vertical_displacement\n")
    f.write("data = Sentinel-1\n")
    f.write("master metadata = {}.xml\n".format(master))
    f.write("slave metadata = {}.xml\n".format(slave))
    f.write("amplitude master = {}.mli.geo.tif\n".format(os.path.join(outdir,master)))
    f.write("amplitude slave = {}.mli.geo.tif\n".format(os.path.join(outdir,slave)))
    f.write("digital elevation model = {}.dem.tif\n".format(os.path.join(outdir,output)))
    f.write("simulated phase = {}.sim_unw.geo.tif\n".format(os.path.join(outdir,output)))
    f.write("filtered interferogram = {}.diff0.man.adf.bmp.geo.tif\n".format(os.path.join(outdir,output)))
    f.write("filtered coherence = {}.adf.cc.geo.tif\n".format(os.path.join(outdir,output)))
    f.write("unwrapped phase = {}.adf.unw.geo.tif\n".format(os.path.join(outdir,output)))
    f.write("vertical displacement = {}.vert.disp.geo.tif\n".format(os.path.join(outdir,output)))
    f.write("mli.par file = {}.mli.par\n".format(os.path.join(outdir,master)))
    f.write("gamma version = {}\n".format(gamma_version))
    f.write("dem source = {}\n".format(dem_source))
    f.write("main log = {}\n".format(logname))
    f.write("processing log = processing.log\n")
    f.close()


def move_output_files(outdir,output,master,prod_dir,long_output,los_flag,inc_flag,look_flag):

    inName = "{}.mli.geo.tif".format(os.path.join(outdir,master))
    outName = "{}_amp.tif".format(os.path.join(prod_dir,long_output))
    shutil.copy(inName,outName)

    inName = "{}.cc.geo.tif".format(os.path.join(outdir,output))
    outName = "{}_corr.tif".format(os.path.join(prod_dir,long_output))
    if os.path.isfile(inName):
        shutil.copy(inName,outName)

# This code uses the filered coherence output from adf command:
#
#    inName = "{}.adf.cc.geo.tif".format(os.path.join(outdir,output))
#    outName = "{}_corr.tif".format(os.path.join(prod_dir,long_output))
#    if os.path.isfile(inName):
#        shutil.copy(inName,outName)
#

    inName = "{}.vert.disp.geo.org.tif".format(os.path.join(outdir,output))
    outName = "{}_vert_disp.tif".format(os.path.join(prod_dir,long_output))
    shutil.copy(inName,outName)

    inName = "{}.adf.unw.geo.tif".format(os.path.join(outdir,output))
    outName = "{}_unw_phase.tif".format(os.path.join(prod_dir,long_output))
    shutil.copy(inName,outName)

    if los_flag:
        inName = "{}.los.disp.geo.org.tif".format(os.path.join(outdir,output))
        outName = "{}_los_disp.tif".format(os.path.join(prod_dir,long_output))
        shutil.copy(inName,outName)
 
    if inc_flag:
        inName = "{}.inc.tif".format(os.path.join(outdir,output))
        outName = "{}_inc.tif".format(os.path.join(prod_dir,long_output))
        shutil.copy(inName,outName)
 
    if look_flag:
        inName = "{}.lv_theta.tif".format(os.path.join(outdir,output))
        outName = "{}_lv_theta.tif".format(os.path.join(prod_dir,long_output))
        shutil.copy(inName,outName)
        inName = "{}.lv_phi.tif".format(os.path.join(outdir,output))
        outName = "{}_lv_phi.tif".format(os.path.join(prod_dir,long_output))
        shutil.copy(inName,outName)
 
    makeAsfBrowse("{}.diff0.man.adf.bmp.geo.tif".format(os.path.join(outdir,output)),
                  "{}_color_phase".format(os.path.join(prod_dir,long_output)))
    
    makeAsfBrowse("{}.adf.unw.geo.bmp.tif".format(os.path.join(outdir,output)),
                  "{}_unw_phase".format(os.path.join(prod_dir,long_output)))


def gammaProcess(masterFile,slaveFile,outdir,dem=None,dem_source=None,rlooks=10,alooks=2,
    inc_flag=False,look_flag=False,los_flag=False,ot_flag=False,cp_flag=False,time=None):

    global proc_log

    logging.info("\n\nSentinel1A differential interferogram creation program\n")
    logging.info("Creating output interferogram in directory {}\n\n".format(outdir))

    #
    #  Set some variables and open log files
    #
    wrk = os.getcwd()
    masterDate = masterFile[17:32]
    masterDateShort = masterFile[17:25]
    slaveDate = slaveFile[17:32]
    slaveDateShort = slaveFile[17:25]
    igramName = "{}_{}".format(masterDate,slaveDate) 
    logname = "{}.log".format(outdir)
    log = open(logname,"w")
    proc_log = open("processing.log","w")
    process_log("starting processing")

    if not "IW_SLC__" in masterFile:
        logging.error("ERROR: Master file {} is not of type IW_SLC!".format(masterFile))
        exit(1)
    if not "IW_SLC__" in slaveFile:
        logging.error("ERROR: Slave file {} is not of type IW_SLC!".format(slaveFile))
        exit(1)
  
    type, pol = getFileType(masterFile)

    if cp_flag:
        if type == "SDV":
            pol = "vh"
        elif type == "SDH":
            pol = "hv"
        else:
            logging.info("Flag type mismatch -- processing {}".format(pol))
        logging.info("Setting pol to {}".format(pol))

    logging.info("Processing the {} polarization".format(pol))

    #
    #  Ingest the data files into gamma format
    #
    process_log("Starting par_s1_slc.py")
    par_s1_slc(pol)
   
    #
    #  Fetch the DEM file
    # 
    process_log("Getting a DEM file")
    if dem is None:
        dem, dem_source = getDemFileGamma(masterFile,ot_flag,alooks,True)
        logging.info("Got dem of type {}".format(dem_source))
    else:
        logging.debug("Value of DEM is {}".format(dem))
        if dem_source is None:
            dem_source = "UNKNOWN"
        logging.info("Found dem type of {}".format(dem_source))

    if not os.path.isdir(outdir):
        os.mkdir(outdir)        

    #
    # Figure out which bursts overlap between the two swaths 
    #
    if time is None:
        (burst_tab1,burst_tab2) = getBurstOverlaps(masterFile,slaveFile)
    else:
        (burst_tab1,burst_tab2) = getSelectBursts(masterFile,slaveFile,time)
        
    logging.info("Finished calculating overlap - in directory {}".format(os.getcwd()))
    shutil.move(burst_tab1,masterDateShort)
    shutil.move(burst_tab2,slaveDateShort)

    #
    # Mosaic the swaths together and copy SLCs over
    #
    process_log("Starting SLC_copy_S1_fullSW.py")
    master = masterDateShort
    slave = slaveDateShort

    path = os.path.join(wrk,outdir)
    os.chdir(master)
    SLC_copy_S1_fullSW(path,master,"SLC_TAB",burst_tab1,mode=1,dem="big",dempath=wrk,raml=rlooks,azml=alooks)
    os.chdir("..")
    os.chdir(slave)
    SLC_copy_S1_fullSW(path,slave,"SLC_TAB",burst_tab2,mode=2,raml=rlooks,azml=alooks)
    os.chdir("..")
    os.chdir(outdir)

    #
    # Interferogram creation, matching, refinement
    #
    process_log("Starting interf_pwr_s1_lt_tops_proc.py 0")
    hgt = "DEM/HGT_SAR_{}_{}".format(rlooks,alooks)
    interf_pwr_s1_lt_tops_proc(master,slave,hgt,rlooks=rlooks,alooks=alooks,iter=3,step=0)
 
    process_log("Starting interf_pwr_s1_lt_tops_proc.py 1")
    interf_pwr_s1_lt_tops_proc(master,slave,hgt,rlooks=rlooks,alooks=alooks,step=1)
 
    process_log("Starting interf_pwr_s1_lt_tops_proc.py 2")
    interf_pwr_s1_lt_tops_proc(master,slave,hgt,rlooks=rlooks,alooks=alooks,iter=3,step=2)

    g = open("offsetfit3.log")
    offset = 1.0
    for line in g:
        if "final azimuth offset poly. coeff.:" in line:
            offset = line.split(":")[1]
    if float(offset) > 0.02:
        logging.error("ERROR: Found azimuth offset of {}!".format(offset))
        exit(1)
    else:
        logging.info("Found azimuth offset of {}!".format(offset))

    output = masterDateShort + "_" + slaveDateShort

    process_log("Starting s1_coreg_overlap")
    cmd  = "S1_coreg_overlap SLC1_tab SLC2R_tab {OUT} {OUT}.off.it {OUT}.off.it.corrected".format(OUT=output)
    execute(cmd,uselogging=True,logfile=log)

    process_log("Starting interf_pwr_s1_lt_tops_proc.py 2")
    interf_pwr_s1_lt_tops_proc(master,slave,hgt,rlooks=rlooks,alooks=alooks,step=3)

    #
    # Perform phase unwrapping and geocoding of results
    #
    process_log("Starting phase unwrapping and geocoding")
    unwrapping_geocoding(master, slave, step="man", rlooks=rlooks, alooks=alooks)

    #
    #  Generate metadata
    #
    process_log("Collecting metadata and output files")

    cmd = "base_init {}.slc.par {}.slc.par - - base > baseline.log".format(master,slave)
    execute(cmd,uselogging=True,logfile=log)
    os.chdir(wrk)
    
    etc_dir =  os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "etc"))
    shutil.copy(os.path.join(etc_dir,"sentinel_xml.xsl"),".")

    cmd = "xsltproc --stringparam path {PATH} --stringparam timestamp timestring --stringparam file_size 1000 --stringparam server stuff --output {M}.xml sentinel_xml.xsl {PATH}/manifest.safe".format(M=master,PATH=masterFile)
    execute(cmd,uselogging=True,logfile=log)
    cmd = "xsltproc --stringparam path {PATH} --stringparam timestamp timestring --stringparam file_size 1000 --stringparam server stuff --output {S}.xml sentinel_xml.xsl {PATH}/manifest.safe".format(S=slave,PATH=slaveFile)
    execute(cmd,uselogging=True,logfile=log)
 
    makeHDF5List(master,slave,outdir,output,dem_source,logname)

    #
    # Move the outputs to the PRODUCT directory
    #
    prod_dir = "PRODUCT"
    if not os.path.exists(prod_dir):
        os.mkdir("PRODUCT") 
    move_output_files(outdir,output,master,prod_dir,igramName,los_flag,inc_flag,look_flag)

    create_readme_file(masterFile,slaveFile,igramName,int(alooks)*20,dem_source,pol)

    process_log("Done!!!")
    logging.info("Done!!!")


if __name__ == '__main__':

  parser = argparse.ArgumentParser(prog='ifm_sentinel.py',
    description='Process Sentinel-1 data into interferograms using GAMMA software')
  parser.add_argument("master",help="Master input file")
  parser.add_argument("slave",help="Slave input file")
  parser.add_argument("output",help="Output igram directory")
  parser.add_argument("-d","--dem",
    help="Input DEM file to use, otherwise calculate a bounding box (e.g. big for big.dem/big.par)")
  parser.add_argument("-r","--rlooks",default=20,help="Number of range looks (def=20)")
  parser.add_argument("-a","--alooks",default=4,help="Number of azimuth looks (def=4)")
  parser.add_argument("-i",action="store_true",help="Create incidence angle file")
  parser.add_argument("-l",action="store_true",help="Create look vector theta and phi files")
  parser.add_argument("-s",action="store_true",help="Create line of sight displacement file")
  parser.add_argument("-o",action="store_true",help="Use opentopo to get the DEM file instead of get_dem")
  parser.add_argument("-c",action="store_true",help="cross pol processing - either hv or vh (default hh or vv)")
  parser.add_argument("-t",nargs=4,type=float,help="Start processing at time for length bursts",
                      metavar=('t1','t2','t3','length'))
  args = parser.parse_args()

  logFile = "ifm_sentinel_log.txt"
  logging.basicConfig(filename=logFile,format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p',level=logging.INFO)
  logging.getLogger().addHandler(logging.StreamHandler())
  logging.info("Starting run")

  gammaProcess(args.master,args.slave,args.output,dem=args.dem,rlooks=args.rlooks,alooks=args.alooks,
    inc_flag=args.i,look_flag=args.l,los_flag=args.s,ot_flag=args.o,cp_flag=args.c,time=args.t)


