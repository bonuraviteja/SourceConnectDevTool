import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import uuid
import sqlparse
from hdbcli import dbapi  # HANA driver

# Folder containing .sql files for views
#sql_folder = "C:/Users/lakshmi.prasanna/OneDrive - insightsoftware/Documents/TEMPLATES_SC_SOURCES/stage/test_templates"

# Database connection details for HANA
hana_config = {
    "address": "10.72.137.28",  # HANA server address
    "port": 30015,  # Default HANA port
    "user": "SC_STG_70",
    "password": "Insight1",
    "database": "SC_STG_70",  # HANA schema or tenant
}

output_dir = "C:/Users/lakshmi.prasanna/OneDrive - insightsoftware/Documents/TEMPLATES_SC_SOURCES/inforLn/scripts"

def clean_object_name(name):
    """Remove schema prefix and clean up object names."""
    return name.split('.')[-1].strip()  # Keep only the object name after the dot

def format_sql(sql_content):
    #formatted = sqlparse.format(sql_content, reindent=True, keyword_case='upper')
    # Remove extra blank lines
    lines = sql_content.splitlines()
    trimmed_lines = [line.strip() for line in lines if line.strip()]  # Remove empty or whitespace-only lines
    return "\n".join(trimmed_lines)

def fetch_procedure_and_table_definitions_hana(object_names, object_type):
    """Fetch DDL definitions for HANA tables and procedures."""
    try:
        conn = dbapi.connect(
            address=hana_config["address"],
            port=hana_config["port"],
            user=hana_config["user"],
            password=hana_config["password"]
        )
        cursor = conn.cursor()
        object_definitions = []

        for object_name in object_names:
            object_name = clean_object_name(object_name)
            if object_type == "PROCEDURE":
                query = f"""
                    SELECT PROCEDURE_NAME AS OBJECT_NAME, DEFINITION AS DEFINITION
                    FROM SYS.PROCEDURES 
                    WHERE PROCEDURE_NAME = '{object_name.upper()}' AND SCHEMA_NAME = '{hana_config["user"]}'
                """
            elif object_type == "TABLE":
                # For tables, HANA does not directly store DDL, so this is a simulated example
                query = f"""CALL table_ddl ('{object_name.upper()}', '{hana_config["user"]}')"""
            elif object_type == "VIEW":
                # For tables, HANA does not directly store DDL, so this is a simulated example
                query = f"""CALL view_ddl ('{object_name.upper()}', '{hana_config["user"]}')"""
            else:
                print(f"Unknown object type: {object_type}")
                continue

            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Debugging: Print rows to inspect their structure
            print(f"Rows for {object_type} {object_name}: {rows}")
            
            for row in rows:
                # Ensure that row has the expected number of columns
                if len(row) >= 2:
                    # Access column values by index
                    object_name_value = row[0]  # The first column (PROCEDURE_NAME)
                    definition = row[1] or ""  # The second column (DEFINITION)

                    # Update procedure definition format
                    if object_type == "PROCEDURE":
                        definition = definition.replace("CREATE PROCEDURE", "CREATE OR REPLACE PROCEDURE")

                    # Append the object definition to the list
                    object_definitions.append({
                        "name": object_name_value,  # Object name
                        "definition": definition,
                        "type": object_type
                    })
                else:
                    print(f"Unexpected number of columns for {object_name}. Row: {row}")

        conn.close()
        return object_definitions

    except Exception as e:
        print(f"Error fetching object definitions: {e}")
        return []


# def read_sql_files(folder):
#     """Read all .sql files in a folder and extract view definitions."""
#     view_definitions = []
#     for file_name in os.listdir(folder):
#         if file_name.endswith(".sql"):
#             file_path = os.path.join(folder, file_name)
#             with open(file_path, "r", encoding="utf-8") as f:
#                 sql_content = f.read()
#                 view_name = file_name.replace(".sql", "").upper()  # Use file name as the view name
#                 view_definitions.append({
#                     "name": view_name,
#                     "definition": sql_content.strip(),
#                     "type": "VIEW"
#                 })
#     return view_definitions

def prettify_xml(elem):
     """Return a formatted XML string with exactly one line between tags."""
     rough_string = ET.tostring(elem, 'utf-8')
     reparsed = minidom.parseString(rough_string)
     pretty = reparsed.toprettyxml(indent="    ")

    # Remove unnecessary blank lines
     lines = pretty.split("\n")
     stripped_lines = [line for line in lines if line.strip()]  # Remove empty lines

    # Join the lines into a single string
     pretty_xml = "\n".join(stripped_lines)

    # Replace &lt; with < and &gt; with >
     pretty_xml = pretty_xml.replace("&lt;", "<").replace("&gt;", ">")
     pretty_xml = pretty_xml.replace("amp;", "")
     return pretty_xml

def update_or_add_object_to_xml(object_definitions, existing_file):
    """Update or add object definitions in the XML, preserving CDATA tags."""
    namespaces = {"xsi": "http://www.w3.org/2001/XMLSchema-instance"}
    ET.register_namespace("xsi", namespaces["xsi"])

    # Parse existing XML or create a new structure if the file doesn't exist
    if os.path.exists(existing_file):
        tree = ET.parse(existing_file)
        scripts = tree.getroot()
        template_items = scripts.find("./Scripts/MxScript/TemplateItems")
    else:
        scripts = ET.Element("Scripts")
        mx_script = ET.SubElement(scripts, "MxScript")
        template_items = ET.SubElement(mx_script, "TemplateItems")
        print("Created new XML structure.")

    # Map existing objects by name for quick lookup
    existing_objects = {
        item.find("Name").text: item for item in template_items.findall("MxTemplateItem")
    }

    # Process each object definition
    for obj in object_definitions:
        file_name = os.path.join(output_dir, f"{obj['name'].upper()}.sql")
        with open(file_name, "w") as sql_file:
            sql_file.write(format_sql(obj['definition']))
        print(f"Generated {file_name}")
        if obj["name"] in existing_objects:
            # Update definition tags for the existing object
            existing_item = existing_objects[obj["name"]]
            raw_def_elem = existing_item.find("RawDefinition")
            def_elem = existing_item.find("Definition")

            if obj["type"] == "TABLE":
                # Update RawDefinition and keep Definition as is
                current_definition_content = def_elem.text if def_elem is not None else "<![CDATA[]]>"
                raw_def_elem.text = f"<![CDATA[{obj['definition']}]]>"
                def_elem.text = f"<![CDATA[{current_definition_content}]]>"
            else:
                # For views/procedures, update both RawDefinition and Definition
                raw_def_elem.text = f"<![CDATA[ ]]>"  # Keep RawDefinition updated
                def_elem.text = f"<![CDATA[{obj['definition']}]]>"  # Update the Definition tag

            print(f"Updated object: {obj['name']} ({obj['type']})")

        else:
            # If the object doesn't exist, add it as a new MxTemplateItem
            item = ET.SubElement(template_items, "MxTemplateItem", {
                "{http://www.w3.org/2001/XMLSchema-instance}type": "MxTableItem" if obj["type"] == "TABLE" else "MxViewItem" if obj["type"] == "VIEW" else "MxProcedureItem"
            })
            ET.SubElement(item, "Uuid").text = str(uuid.uuid4())
            ET.SubElement(item, "Name").text = obj["name"].upper()
            
            # Ensure the CDATA wrapping for RawDefinition and Definition
            if obj["type"] == "TABLE":
                ET.SubElement(item, "RawDefinition").text = f"<![CDATA[{obj['definition']}]]>"
                ET.SubElement(item, "Definition").text = "<![CDATA[]]>"  # No definition content for tables
            else:
                ET.SubElement(item, "RawDefinition").text = "<![CDATA[ ]]>"  # No raw definition for views/procedures
                ET.SubElement(item, "Definition").text = f"<![CDATA[{obj['definition']}]]>"

            print(f"Added new object: {obj['name']} ({obj['type']})")
            
    for existing_item in existing_objects.values():
        raw_def_elem = existing_item.find("RawDefinition")
        def_elem = existing_item.find("Definition")

        # Check for the presence of the <RawDefinition> tag
        if raw_def_elem is not None:
            # If <RawDefinition> exists but is improperly formatted, fix it
            if raw_def_elem.text is None or not raw_def_elem.text.startswith("<![CDATA["):
                raw_def_elem.text = f"<![CDATA[{raw_def_elem.text}]]>"  # Ensure CDATA wrapping for valid content
        else:
            # If the opening tag is missing but the closing tag exists, recreate <RawDefinition>
            raw_def_elem = ET.SubElement(existing_item, "RawDefinition")
            raw_def_elem.text = f"<![CDATA[{raw_def_elem.text}]]>"  # Add an empty CDATA structure

        # Ensure <Definition> is similarly well-formed
        if def_elem is not None:
            if def_elem.text is None or not def_elem.text.startswith("<![CDATA["):
                def_elem.text = f"<![CDATA[{def_elem.text}]]>"  # Ensure CDATA wrapping for valid content
        else:
            # If <Definition> tag is completely missing, add it
            def_elem = ET.SubElement(existing_item, "Definition")
            def_elem.text = f"<![CDATA[{def_elem.text}]]>" # Add an empty CDATA structure

    

           # print(f"Ensured CDATA wrapping for existing object: {existing_item.find('Name').text}")

    # Prettify and save updated XML
    pretty_xml = prettify_xml(scripts)

    # Backup logic
    backup_file = existing_file + ".bak"
    if os.path.exists(backup_file):
        os.remove(backup_file)  # Remove existing backup
    os.rename(existing_file, backup_file)  # Create the backup

    with open(existing_file, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    print(f"XML file updated. Backup saved as: {backup_file}")



if __name__ == "__main__":
    # Read view definitions from the folder
    #view_definitions = read_sql_files(sql_folder)

    # Fetch procedure and table definitions from HANA
    objects_to_process = [       
        {"name": "TEST_VIEW", "type": "VIEW"}
        {"name": "AP_BKPF_VIEW", "type": "VIEW"},
        {"name": "FIN_HEADER_TEST", "type": "TABLE"},
        {"name": "AP_FIN_PYMT_TRX", "type": "TABLE"},
       {"name": "TEST_PROCEDURE", "type": "PROCEDURE"},
       {"name": "AIF_ERROR_PROC", "type": "PROCEDURE"} 
        
    ]

    object_definitions = []
    for obj in objects_to_process:
        definitions = fetch_procedure_and_table_definitions_hana([obj["name"]], obj["type"])
        object_definitions.extend(definitions)

    if object_definitions:
        # Update existing XML file
        existing_file = "C:/Users/lakshmi.prasanna/OneDrive - insightsoftware/Documents/TEMPLATES_SC_SOURCES/stage/test_templates/Staging Area HANA SC Template (7)/Staging Area HANA SC Template/STAGE/Staging Area HANA SC Template.xml"
        update_or_add_object_to_xml(object_definitions, existing_file)
    else:
        print("No object definitions retrieved.")

    # procedures_to_process = ["TEST_PROCEDURE","AIF_ERROR_PROC"]  # Add your procedure names here
    # tables_to_process = ["MDR_GL_ACCOUNT_STG","FIN_HEADER"]  # Add your table names here
    # views_to_process = ["TEST_DEC_VIEW","AP_BKPF_VIEW"]  # Add your table names here

    # procedure_definitions = fetch_procedure_and_table_definitions_hana(procedures_to_process, "PROCEDURE")
    # table_definitions = fetch_procedure_and_table_definitions_hana(tables_to_process, "TABLE")
    # view_definitions = fetch_procedure_and_table_definitions_hana(views_to_process, "VIEW")

    # # Combine all definitions
    # all_definitions = view_definitions + procedure_definitions + table_definitions

    # if all_definitions:
    #     xml_file = "C:/Users/lakshmi.prasanna/OneDrive - insightsoftware/Documents/lokanath/testing/Staging Area HANA SC Master Data Template/Staging Area HANA SC Master Data Template/Stage/Staging Area HANA SC Master Data Template.xml"
    #     update_or_add_object_to_xml(all_definitions, xml_file)
    # else:
    #     print("No object definitions found.")





  #the scenarios to be covered 

  #1. when ever there is any update in the existing view ,defination has to be updation ,keeping raw defination empty 
  #2. when ever there is any new object (table,view,procedure) that object has to be created in the xml with proper tags and all 
  #3. in case of  new object table the raw definition has to get updated ,leaving the definition tag emtpy which later need to be filled by content to drop or create or just skip if exists 
  #4. in case of old table object the raw defination has to be updated leaving the defination tag remain same
  #5. need to check sync feature and all 


  
  #to  list of views in database 
# select upper(VIEW_NAME) as Name,'{"name":"'||upper(VIEW_NAME)||'","type":"VIEW"},' objectname , create_time  FROM VIEWS
# WHERE SCHEMA_NAME = 'SC_STG_70'
# ORDER BY create_time desc;


#to  list of procedures in databse 


# select upper(PROCEDURE_NAME) as Name,'{"name":"'||upper(PROCEDURE_NAME)||'","type":"PROCEDURE"},' objectname , create_time  FROM SYS.PROCEDURES
# WHERE SCHEMA_NAME = 'SC_STG_70'
# ORDER BY create_time desc;



#to  list of tables in database

# select upper(TABLE_NAME) as Name,'{"name":"'||upper(TABLE_NAME)||'","type":"TABLE"},' objectname , create_time  FROM SYS.TABLES
# WHERE SCHEMA_NAME = 'SC_STG_70'
# ORDER BY create_time desc;
