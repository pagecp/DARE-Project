import json
import pdb
import pe_enes as ps
from dispel4py.workflow_graph import WorkflowGraph
from dispel4py.base import IterativePE, ProducerPE, ConsumerPE
from dispel4py.core import GenericPE

""" 
A Python program to demonstrate the adjacency 
list representation of the graph 
"""

map_proc_elem = {"0":"PreProcess_multiple_scenario",
"1":"IcclimProcessing",
"2":"StreamProducer",
"3":"NetCDF2xarray",
"4":"ReadNetCDF",
"5":"StandardDeviation",
"6":"AverageData",
"7":"CombineScenario",
"8":"PlotMultipleScenario",
"9":"B2DROP"}

#TODO add a proc elem to create netcdf for standarddeviation and AverageData

src_to_dest = {"0":[1],
		"1":[1,5,6,9],
		"2":[1],
		"3":[None],
		"4":[5,6],
		"5":[7],
		"6":[7],
		"7":[8],
		"8":[9]}

prev_proc_required = {"0":[None],
		"1":[0],
		"2":[None],
		"3":[None],
		"4":[1],
		"5":[4],
		"6":[4],
		"7":[5,6],
		"8":[7]
}

		
class Climate_Workflow(WorkflowGraph):

	def __init__(self, param):
		
		WorkflowGraph.__init__(self)
		self.param = param
		self.preprocess = None
		self.num_block = 1
		self.nb_block = len(param)
		self.combine_proc_elem = None

		#Check B2DROP id
		param_workflow = self.param['Workflow'][0]
		b2drop = [i for i in [*param_workflow] if 'B2DROP' in i]
		if b2drop:
			self.b2drop_id = param_workflow[b2drop[0]]

	def create_workflow(self, **kwargs):
		
		param = self.param['PE']
		name_first_pe = [*self.param][0]
		prev_proc_elem = self.preprocess

		list_kwargs = [*kwargs]

		if 'scenario' in kwargs:
			scenario_name = kwargs['scenario']
		else:
			scenario_name = ""

		num_block=self.num_block
		list_block=[*param]
		block = list_block[num_block-1]

		nb_nodes = len(param[block])
		num_node = 1
		list_proc_elem = []

		for node in param[block]:

			if num_block>1 and num_node==1:
				prev_proc_elem = self.combine_proc_elem
				num_node+=1
				continue

			elif num_block==1 and num_node==1:
				prev_prov_elem=self.preprocess

			for proc_elem in param[block][node]:

				if num_node>1 and list_proc_elem:
					prev_proc_elem = list_proc_elem[0]

				name_proc_elem = '{0}_{1}_{2}'.format(node,proc_elem[:-2],scenario_name)

				try:
					if proc_elem=='B2DROP()':
						exec(name_proc_elem+"=ps."+proc_elem[:-2]+"(self.b2drop_id)")
						exec(name_proc_elem+".name=name_proc_elem")
					else:
						exec(name_proc_elem+"=ps."+proc_elem)
						exec(name_proc_elem+".name=name_proc_elem")
				except AssertionError as error:
					print(error)

				#This condition aims to connect the last node of one block with the next block
				if num_node==nb_nodes and num_block<self.nb_block:
					self.connect(eval(name_proc_elem), 'output', self.combine_proc_elem, scenario_name)

				list_proc_elem.append(eval(name_proc_elem))

				#print('{0}  {1}'.format(prev_proc_elem.name, name_proc_elem))

				self.connect(prev_proc_elem, 'output', eval(name_proc_elem), 'input')

			num_node+=1



class Multiple_scenario(Climate_Workflow):

	def __init__(self, param):
		Climate_Workflow.__init__(self, param)
		name_first_node = [*self.param['Workflow'][0]][0]
		self.nb_scenario = len(self.param['Workflow'][0][name_first_node]['in_files'])
		self.combine_proc_elem = None
		self.multiple_scenario_ = True
		self.nb_block = len(self.param['PE'])

	def multiple_scenario(self):

		#Main preprocessing element 
		preprocess = ps.PreProcess_multiple_scenario()
		preprocess.name = "Workflow"
		self.preprocess = preprocess

		#Processing element to combine the multiple scenario
		if self.nb_block>1:
			combine_proc_elem = ps.CombineScenario(self.nb_scenario)
			combine_proc_elem.name = "combine_scenario"
			self.combine_proc_elem = combine_proc_elem
	
		param_workflow = self.param['PE']

		for block in param_workflow:

			if block=='Block_1':	
				for scenario in range(self.nb_scenario):
					scenario_name = "scenario_"+str(scenario+1)
					kwargs = {'scenario':scenario_name}
					self.create_workflow(**kwargs)
			elif block=='Block_2':
				self.create_workflow()	

			self.num_block+=1

save_path = '/tmp/'

def check_order(inputs):
    list_key = [*inputs]
    list_key.sort()
    new_inputs = OrderedDict()
    for input_name in list_key:
        new_inputs[input_name] = inputs[input_name]
    return new_inputs


def remove_absolute_path(string_name, charact):
    pos_char = [pos for pos, char in enumerate(string_name) if char == charact]
    return string_name[pos_char[-1]+1::]

def map_multiple_scenario(inputs):
    #create dictionary to map the scenario
    first_node = [*inputs][0]
    list_scenario = inputs[first_node]['in_files']
    nb_scenario = len(list_scenario)

    map_scenario = OrderedDict()
    map_out_files = OrderedDict()

    for scenario in range(nb_scenario):
        map_scenario['scenario_'+str(scenario+1)] = list_scenario[scenario]
        map_out_files['scenario_'+str(scenario+1)] = 'scenario_'+str(scenario+1)+'.nc'

    inputs['in_files'] = map_scenario
    inputs['out_file'] = map_out_files
    inputs['indice_name'] = inputs[first_node]['indice_name']

    return inputs

def get_netCDFProcessing(list_PE, inputs):

    test = ["NetCDFProcessing" in s for s in list_PE]

    #check if there's any known processing element NetCDFProcessing
    ncdf_bool = [bool_ for bool_, x in enumerate(test) if x]
    if ncdf_bool:
        i = 0
        for ncdf in test:
            if ncdf and inputs[list_PE[i]]['out_file'] is None:
                inputs[list_PE[i]]['out_file'] = save_path+list_PE[i]+'.nc'
            i+=1
    else:
        for l_pe in list_PE:
            inputs[l_pe]['out_file'] = save_path+l_pe+'.nc'

    return inputs


class IcclimProcessing(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_input('input')
        self._add_output('output')

    def _process(self, parameters):
        #Find PE named PE{num}_IcclimProcessing

        pdb.set_trace()

        from icclim import icclim

        ind_scenario = self.name.find("scenario_")
        name_scenario = self.name[ind_scenario::]
        name_node = self.name[:ind_scenario-1]
        pdb.set_trace()
        param = parameters['input'][name_node]
        path_files = parameters['input']

        icclim_param = {
            'indice_name':param['indice_name'],
            'slice_mode':param['slice_mode'],
            'var_name':param['var_name'],
            'in_files':path_files['in_files'][name_scenario],
            'out_file':path_files['out_file'][name_scenario]
        }

        icclim.indice(**icclim_param)

        self.write('output', ({'out_file':path_files['out_file'][name_scenario],
        'indice_name':param['indice_name']}))

class PreProcess_multiple_scenario(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_output('output')    

    def _process(self, inputs):
        #Map the scenario in an ordererdict
        inputs = map_multiple_scenario(inputs)

        #We sort the processing element in inputs to be
        new_inputs = check_order(inputs)

        self.write('output', new_inputs)



class StreamProducer(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_output('output')

    def _process(self, inputs):
        list_PE = inputs.keys()
        len_lc = len(list_PE)

        #get processing element NetCDFProcessing
        inputs = get_netCDFProcessing(list_PE, inputs)

        #Sort the Processing Element on the right order
        new_inputs = check_order(inputs)
        self.write('output', new_inputs)


class NetCDF2xarray(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_input('input')
        self._add_output('output')

    def _process(self, parameters):
        import xarray as xr

        ds = xr.open_dataset(parameters['input'][1]['result_nc'])

        self.write('output', (ds, [parameters['input'][-1]]))


class ReadNetCDF(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_input('input')
        self._add_output('output')

    def _process(self, parameters):
        #Load the netcdf file
        from netCDF4 import Dataset
        import netcdftime

        nc = Dataset(parameters['input'][1]['result_nc'])

        #Extracting the time and change the time format from num to date time
        time = nc.variables['time']
        nc_time = netcdftime.utime(time.units, time.calendar)
        date_time = nc_time.num2date(time[:])

        var = nc.variables[parameters['input'][0]['indice_name']][:]

        self.write('output', (date_time, var))


class StandardDeviation(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_input('input')
        self._add_output('output')

    def _process(self, parameters):

        from netCDF4 import Dataset
        import netcdftime

        nc = Dataset(parameters['input']['out_file'])

        #Extracting the time and change the time format from num to date time
        time = nc.variables['time']
        nc_time = netcdftime.utime(time.units, time.calendar)
        date_time = nc_time.num2date(time[:])

        var = nc.variables[parameters['input']['indice_name']][:]
        import numpy as np
        #time = parameters['input'][0]
        #var = parameters['input'][1]
        var = np.reshape(var, (var.shape[0], -1))
        result = np.std(var, axis=1)

        self.write('output',  (time, result, self.name))


class AverageData(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_input('input')
        self._add_output('output')

    def _process(self, parameters):
        from netCDF4 import Dataset
        import netcdftime

        ind_scenario = self.name.find("scenario_")
        name_scenario = self.name[ind_scenario::]

        nc = Dataset(parameters['input']['out_file'])

        #Extracting the time and change the time format from num to date time
        time = nc.variables['time']
        nc_time = netcdftime.utime(time.units, time.calendar)
        date_time = nc_time.num2date(time[:])

        var = nc.variables[parameters['input']['indice_name']][:]
        import numpy as np
        #time = parameters['input'][0]
        #var = parameters['input'][1]
        var = np.reshape(var, (var.shape[0], -1))
        result = np.mean(var, axis=1)

        self.write('output', (time, result, self.name))


class CombineData(GenericPE):
    def __init__(self, nb_scenario):
        GenericPE.__init__(self)
        self._add_input('input')
        self._add_output('output')
    
    def _process(self, parameters):
        import numpy as np

        var = parameters['input'][1]
        var = np.reshape(var, (var.shape[0], -1))
        result = np.mean(var, axis=1)

        self.write('output', (parameters['input'], result))


class CombineScenario(GenericPE):
    def __init__(self, nb_scenario):
        GenericPE.__init__(self)

        import numpy as np

        for i in range(nb_scenario):
            name_scenario = 'scenario_'+str(i+1)
            self._add_input(name_scenario,grouping=[1])

        self.nb_scenario = nb_scenario
        self._add_output('output')
        self.mat=0
        self.time=0
        self.count=0
        
    def _process(self, inputs):
        import numpy as np
        
        name_scenario = [*inputs][0]

        if self.count==0:
            self.time = inputs[name_scenario][0]
            var = inputs[name_scenario][1]
            self.mat = np.zeros((self.nb_scenario,len(var)))

            #We move from num to date format because if we send a netcdf variable format we have this error:
            #*** NotImplementedError: Variable is not picklable
            import netcdftime
            t = netcdftime.utime(self.time.units, self.time.calendar) 
            self.time = t.num2date(self.time[:]) 

        self.mat[self.count,:]=inputs[name_scenario][1]
        self.count+=1

        if self.count==(self.nb_scenario):
            self.write('output', (self.time,self.mat))


class PlotMultipleScenario(GenericPE):
    def __init__(self):
        GenericPE.__init__(self)
        self._add_input('input')


    def _process(self, parameters):

        import matplotlib.pyplot as plt
        import numpy as np
        #plt.switch_backend('agg')
        name_var = [*parameters][0]

        time = parameters[name_var][0]
        var = parameters[name_var][1]
        year_list = np.array([t.year for t in time])
        #year_array = np.tile(year_list,(len(var),1))


        plt.figure()
        for i in range(len(var)):
            plt.plot(year_list, var[i,:], label='scenario_'+str(i+1))
        plt.legend()
        plt.xlabel('Year')
        plt.ylabel(self.name)
        plt.grid()

        name_fig = self.name+".png"
        plt.savefig("/tmp/"+name_fig)

        self.write("output", ("/tmp/"+name_fig, name_fig))


class B2DROP(GenericPE):
    def __init__(self, id):
        GenericPE.__init__(self)
        self._add_input('input')
        self._add_output('output')
        self.username = id['username']
        self.password = id['password']

    def _process(self, parameters):
        import owncloud
        
        param = parameters['input'][0]
        name_dir = "enes_usecase"

        if isinstance(param, str):
            src_path = parameters['input'][0]
            upload_path = name_dir+"/"+parameters['input'][1]
        else:
            param_keys = parameters['input'][0].keys()
            src_path = param[param_keys[-2]]['out_file'] 
            upload_path = remove_absolute_path(src_path, '/')
            upload_path = name_dir+"/"+upload_path

        oc = owncloud.Client('https://b2drop.eudat.eu')

        oc.login(self.username, self.password)

        oc.put_file(upload_path, src_path)

        link_info = oc.share_file_with_link(upload_path)
        print("Shared linked is: "+link_info.get_link())


json_path = 'input_C4I.json'
with open(json_path) as json_data:
	input_C4I = json.load(json_data)

clim_workflow = Multiple_scenario(param=input_C4I)
clim_workflow.multiple_scenario()

