### INITIATION ##########################################################################################
import pandas as pd
import requests, urllib3
import io, os
from datetime import datetime
import zipfile
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

path = r"G:\.shortcut-targets-by-id\1vVvQ8R0vPkFcqhXIA6az8I1Qa9cqBZyp\PANAMBY CAPITAL NETWORK\PUBLICO\Crédito Privado, 2023\Analises\4. Bases de dados\Dados_Setoriais\Agribusiness\Input"  # Directory path
os.chdir(path)

Folder = 'INMET'

today = datetime.today()
currentYear = today.year
maxYear = currentYear - 1
#maxYear = 2001

concurrentYear = today.year
url_list = []
fn_list = []
print('Getting url...')
for y in range(maxYear, concurrentYear + 1):
    url = 'https://portal.inmet.gov.br/uploads/dadoshistoricos/' + str(y) + '.zip'
    file = str(y) + '.zip'
    url_list.append(url)
    fn_list.append(file)

for i in range(0, len(url_list)):
    url = url_list[i]
    file = fn_list[i]
    year = file[0:4]
    print('Starting ', file, ' ...')
    if int(year) <= concurrentYear:
        if int(year) < 2020:
            saveLoc = Folder + '/Unzip'
        else:
            saveLoc = Folder + '/Unzip/' + year
        tries = 0
        while tries < 2:
            try:
                response = requests.get(url, verify=False)
                if response.status_code == 200:
                    with io.BytesIO(response.content) as buf:
                        try:
                            with zipfile.ZipFile(buf) as z:
                                for file_info in z.infolist():
                                    directory = saveLoc + '/' + os.path.dirname(file_info.filename)  # Extract the dir
                                    if not os.path.exists(directory):  # Check if the directory exists, if not, create
                                        os.makedirs(directory)

                                    z.extract(file_info, directory)
                                print('Done: ', file)
                                break
                        except zipfile.BadZipFile:
                            tries += 1
                            print(f'ZipFile Error with file: {file}')
                        except Exception as e:
                            tries += 1
                            print(f'An error occurred with file: {file}. Error: {e}')
                else:
                    print(f'Failed to download file: {file}. HTTP status code: {response.status_code}')
            except Exception as e:
                tries += 1
                print(f'An error occurred while processing file: {file}. Error: {e}')

print('Get Done...')

for f in os.listdir(Folder + '/Unzip'):
    try:
        if float(f) < maxYear:
            continue
    except:
        pass
    print(f)
    folder = Folder + '/Unzip/' + f
    print(f'At folder: {folder}')
    try:
        filesInFolder = os.listdir(folder)
        df_list = []
        for file in filesInFolder:
            path = folder + '/' + file

            df = pd.read_csv(path, skiprows=8, sep=';', encoding='latin1', decimal=',')
            df['Region'] = file.split('_')[1]
            df['State'] = file.split('_')[2]
            df['Station'] = file.split('_')[3]
            df['City'] = file.split('_')[4]
            df_list.append(df)
    except:
        print('Error')

    print('Combining...')
    data = pd.concat(df_list)

    x = ['PRESSAO ATMOSFERICA AO NIVEL DA ESTACAO, HORARIA (mB)',
         'PRESSÃO ATMOSFERICA MAX.NA HORA ANT. (AUT) (mB)',
         'PRESSÃO ATMOSFERICA MIN. NA HORA ANT. (AUT) (mB)',
         'RADIACAO GLOBAL (KJ/m²)', 'RADIACAO GLOBAL (Kj/m²)',
         'TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C)',
         'TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C)',
         'TEMPERATURA ORVALHO MAX. NA HORA ANT. (AUT) (°C)',
         'TEMPERATURA ORVALHO MIN. NA HORA ANT. (AUT) (°C)',
         'UMIDADE REL. MAX. NA HORA ANT. (AUT) (%)',
         'UMIDADE REL. MIN. NA HORA ANT. (AUT) (%)',
         'UMIDADE RELATIVA DO AR, HORARIA (%)',
         'VENTO, DIREÇÃO HORARIA (gr) (° (gr))', 'VENTO, RAJADA MAXIMA (m/s)',
         'VENTO, VELOCIDADE HORARIA (m/s)', 'Unnamed: 19']
    existing_cols = [col for col in x if
                     col in data.columns]
    data = data.drop(existing_cols, axis=1)

    try:
        data['DateFinal'] = pd.to_datetime(data['DATA (YYYY-MM-DD)'])
    except:
        pass
    try:
        data['DateFinal'] = pd.to_datetime(data['Data'])
    except:
        pass
    #data['DateFinal'] = data['DATA (YYYY-MM-DD)']
    existing_cols = [col for col in ['DATA (YYYY-MM-DD)', 'HORÁRIO (mm)', 'HORA (UTC)', 'Hora UTC', 'Data'] if
                     col in data.columns]
    data = data.drop(existing_cols, axis=1)
    data.columns = ['Rainfall_mm', 'Temperature_C_Air', 'Temperature_C_Orvalho', 'Region', 'State', 'Station', 'City',
                    'Date']
    data['Rainfall_mm'] = data['Rainfall_mm'].astype(float)
    data['Temperature_C'] = data['Temperature_C_Air'].astype(float)
    # data['Temperature_C'] = data['Temperature_C_Orvalho'].astype(float)
    data = data[data.Rainfall_mm != -9999]
    data = data[data.Temperature_C_Air != -9999]
    # data = data[data.Temperature_C_Orvalho != -9999]
    data = data[data.City != 'CRIOSFERA']

    data['Date'] = data['Date'].dt.to_period('M')

    rainfall = data.pivot_table(values=['Rainfall_mm'], index=['Region', 'State', 'Station', 'City', 'Date'],
                                aggfunc='sum').reset_index()
    temperature1 = data.pivot_table(values=['Temperature_C_Air'], index=['Region', 'State', 'Station', 'City', 'Date'],
                                    aggfunc='mean').reset_index()
    # temperature2 = data.pivot_table(values=['Temperature_C_Orvalho'], index=['Region', 'State', 'Station', 'City', 'Date'],
    #                                 aggfunc='mean').reset_index()

    rainfall['Key'] = rainfall['Region'] + rainfall['State'] + rainfall['Station'] + \
                      rainfall['City'] + rainfall['Date'].astype(str)
    temperature1['Key'] = temperature1['Region'] + temperature1['State'] + temperature1['Station'] + \
                          temperature1['City'] + temperature1['Date'].astype(str)
    data = pd.merge(rainfall, temperature1, on='Key', how='outer')
    data = data.filter(['Region_x', 'State_x', 'Station_x', 'City_x', 'Date_x', 'Rainfall_mm', 'Temperature_C_Air'], axis=1)
    data.columns = ['Region', 'State', 'Station', 'City', 'Date', 'Rainfall_mm', 'Temperature_C_Air']

    path = Folder + f'/Years DB/INMET_{f}.csv'
    if path.split('.')[1] != 'ini':
        data.to_csv(path, sep=';', decimal=',', index=False, encoding='latin1')
    print(f'Done with {f}')

df_list = []
path = Folder + '/Years DB'
for f in os.listdir(path):
    try:
        f_path = path + '/' + f
        df = pd.read_csv(f_path, sep=';', encoding='latin1', decimal=',')
        df['Year'] = int(f.split('_')[1].split('.')[0])
        df_list.append(df)
    except:
        print(f'Error in {f}')
DB = pd.concat(df_list)
print('Saving data...')

path = Folder + '/INMET.csv'
DB.to_csv(path, sep=';', decimal=',', index=False)

print('### DONE ###')


