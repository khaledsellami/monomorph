import os
import re
from typing import Optional
import logging

from monomorph.const import ApproachType
from monomorph.execution.dependency.buildfile import REQUIRED_DEPENDENCIES, CLIENT_REQUIRED_DEPENDENCIES, \
    SERVER_REQUIRED_DEPENDENCIES
from monomorph.execution.microservice import MicroserviceDirectory
from monomorph.execution.project import MicroservicesProject
from monomorph.planning.proxies import PlannedAPIClass


class ReportWriter:
    def __init__(self, project: MicroservicesProject):
        self.project = project
        self.logger = logging.getLogger("monomorph")

    def generate_report(self, api_classes: dict[str, PlannedAPIClass], metadata: Optional[dict] = None):
        self._write_report(api_classes, metadata)
        for microservice in self.project.microservices.values():
            self.generate_microservice_report(microservice, api_classes)

    def _write_report(self, api_classes: dict[str, PlannedAPIClass], metadata: Optional[dict] = None):
        report_path = os.path.join(self.project.project_path, "REFACTORING_REPORT.md")
        report_lines = []
        report_lines.append(f"# Refactoring Report for application \"{self.project.app_name}\"")
        report_lines.append(" This report contains some of the details of the refactoring process applied to "
                            "the application. For more details on the refactoring changes, please refer to "
                            "the reports `<ms_name>/REFACTORING_REPORT.md` for each microservice.")
        report_lines.append(f"## Project Details")
        report_lines.append(f"- **Application Name**: {self.project.app_name}")
        report_lines.append(f"- **Package Name**: {self.project.package_name}")
        report_lines.append(f"- **Decomposition**: {self.project.decomposition.name}")
        report_lines.append(f"- **Programming Language**: {self.project.decomposition.language}\n")
        report_lines.append(f"- **Java Version**: {self.project.java_version}")
        report_lines.append(f"- **Build Tool**: {self.project.build_tool.capitalize()}")
        classes = {c for ms in self.project.decomposition.partitions for c in ms.classes}
        report_lines.append(f"- **Number of unique classes**: {len(classes)}")
        report_lines.append(f"- **Number of microservices**: {len(self.project.microservices)}")
        report_lines.append(f"## Refactoring Details")
        report_lines.append(f"- **Number of new API classes**: {len(api_classes)}")
        report_lines.append(f"- **Number of DTO-based API classes**: "
                            f"{len([c for c in api_classes.values() if c.decision != ApproachType.ID_BASED])}")
        report_lines.append(f"- **Number of ID-based API classes**: "
                            f"{len([c for c in api_classes.values() if c.decision == ApproachType.ID_BASED])}")
        report_lines.append("\n---\n")
        report_lines.append(f"## Microservices")
        for ms_name, microservice in self.project.microservices.items():
            original_name = microservice.name
            codename = microservice.uid
            path = os.path.relpath(microservice.directory_path, self.project.project_path)
            ms_rel_path = os.path.join(path, "REFACTORING_REPORT.md")
            report_lines.append(f"- **Microservice \"{original_name}\"**:")
            report_lines.append(f"  - Code name: `{codename}`")
            report_lines.append(f"  - Path: \"[{path}]({path})\"")
            report_lines.append(f"  - Report: \"[{ms_rel_path}]({ms_rel_path})\"")
            if microservice.exposes_services():
                report_lines.append(f"  - Listen Port: {microservice.port}")
        report_lines.append("\n---\n")
        report_lines.append(f"## Approach Description")
        report_lines.append(f"The \"MonoMorph\" refactoring process generates a ID and DTO based microservices architecture "
                            f"using an agentic approach combining LLMs and Modeling to transform a monolithic application into "
                            f"a microservices architecture. In the ID based design, each microservice is responsible for the "
                            f"lifecycle of the class it owns. The rest consume it through its unique ID and calls "
                            f"to the corresponding API. In this implementation, the interaction between microservices is "
                            f"done through gRPC. The lifecycle of the classes is managed by a leasing/TTL (time-to-live) system. "
                            f"The DTO based design is a more traditional approach where each microservice exposes its own API and "
                            f" the classes are transferred through the network in each interaction. To combine the simplicity of "
                            f"the DTO approach when possible and the ID based approach when needed, the MonoMorph process generates a hybrid "
                            f"architecture where the selection of the refactoring approach for each candidate API class is done "
                            f"by the LLM.")
        report_lines.append(f"")
        report_lines.append("The process is divided into the following steps:")
        report_lines.append(f"1. **Dependency Analysis**: The process starts by analyzing the dependencies between "
                            f"the classes in the monolithic application.")
        report_lines.append(f"2. **Detecting new APIs**: The process detects the new APIs that need to be created for each "
                            f"microservice.")
        report_lines.append(f"3. **Approach Selection**: The process selects the approach for each API class using the agentic LLM.")
        report_lines.append(f"4. **Post-decision**: The process analyzes the inter-service interactions, taking into account "
                            f"the selected approach to find any potential new API classes (which will be asigned to the DTO method).")
        report_lines.append(f"5. **Refactoring**: For each new API class, the process uses a LLM to generate a protocol buffer "
                            f"definition and its corresponding gRPC server and client implementations. "
                            f"The implementation and design differ based on the chose approach.")
        report_lines.append(f"6. **Configuration Generation**: The process generates and adds the helper classes to the "
                            f"microservices. It updates as well the dependencies of the build tool.")
        report_lines.append(f"7. **Entrypoint Generation**: The process generates the entry point for each microservice "
                            f"ensuring that each gRPC server is configured and integrates the process into the original main if needed.")
        report_lines.append(f"8. **Report Generation**: The current report is generated for the project and each microservice ensuring "
                            f"tracing of the transformations and their explanations.")
        # Decisions section
        report_lines.append("\n---\n")
        report_lines.append("\n---\n")
        report_lines.append(f"## Decisions and Explanations")
        report_lines.append(f" The following section provides the reasoning behind the decisions made for the refactoring approach:")
        for class_name, api_class in api_classes.items():
            report_lines.append(f" - Class `{class_name}`:")
            report_lines.append(f"   - Decision: `{api_class.decision.value}`")
            report_lines.append(f"   - Reasoning: {api_class.reasoning}")
            report_lines.append(f"\n---\n")
        if metadata:
            report_lines.append("\n---\n")
            report_lines.append(f"## Refactoring Metadata")
            for key, value in metadata.items():
                report_lines.append(f"- **{key}**: {value}")
        self.project.logger.debug(f"Writing project report to {report_path}")
        with open(report_path, "w") as f:
            f.write("\n".join(report_lines))

    def generate_microservice_report(self, microservice: MicroserviceDirectory, api_classes: dict[str, PlannedAPIClass]):
        """
        Generate a report for the microservice.
        """
        lines = []
        lines.append(f"# **Microservice \"{microservice.name}\" (\"{microservice.uid}\") Report**")
        ## Summary Section
        lines.append(f"## Microservice Summary")
        renamed = f"(renamed \"{microservice.uid}\" in pathing and identification)" if microservice.name != microservice.uid else ""
        n_classes = len(microservice.partition.classes)
        n_duplicates = len(microservice.partition.duplicated_classes)
        java_helpers = [f for f in microservice._included_helpers if f.endswith(".java")]
        n_new_classes = (len(microservice.new_server) + len(microservice._new_client) + len(java_helpers) + len(microservice._generated_helpers)
                         + bool(microservice._entrypoint_grpc_details) + bool(microservice._combined_main_details) + len(microservice._new_other))
        n_new_proto = len(microservice._new_proto) + len([f for f in microservice._included_helpers if f.endswith(".proto")])
        n_total = n_classes + n_duplicates + n_new_classes + n_new_proto
        # txt_start = f" The microservice \"{microservice.name}\" {renamed} contains **{n_classes}** classes from the decomposition file"
        txt_start = f" The microservice \"{microservice.name}\" {renamed} contains a total of **{n_total}** classes and files:"
        decomp_txt = f"**{n_classes}** classes were selected from the decomposition file"
        duplicates_txt = f"**{n_duplicates}** class{'es were' if n_duplicates != 1 else ' was'} added as duplicate" if n_duplicates else ""
        new_classes_txt = f"**{n_new_classes}** new class{'es were' if n_new_classes != 1 else ' was'} added or generated" if n_new_classes else ""
        new_proto_txt = f"**{n_new_proto}** new proto file{'s were' if n_new_proto != 1 else ' was'} added or generated" if n_new_proto else ""
        lines.append(txt_start)
        lines.extend(["  - " + t for t in [decomp_txt, duplicates_txt, new_classes_txt, new_proto_txt] if t])
        # txt_list = [t for t in [txt_start, duplicates_txt, new_classes_txt, new_proto_txt] if t]
        # if len(txt_list) > 1:
        #     last_txt = txt_list[-1]
        #     txt = ", ".join(txt_list[:-1]) + " and " + last_txt + "."
        # else:
        #     txt = txt_start + "."
        # lines.append(txt)
        lines.append("")
        if microservice._old_entrypoint_class:
            old_main = microservice._old_entrypoint_class.split(".")[-1]
            old_main_path = None
            for file_source, file_path in microservice.file_map.items():
                if file_source.endswith(old_main + ".java"):
                    old_main_path = os.path.relpath(file_path, microservice.directory_path)
                    break
            if not old_main_path:
                microservice.logger.warning(f"Old main class {old_main} not found in microservice {microservice.uid}.")
                old_main_link = old_main
            else:
                old_main_link = f"[{old_main}]({old_main_path})"
        else:
            old_main_link = None
        if microservice._combined_main_details:
            combined_main = microservice._combined_main_details["class_name"]
            combined_path = os.path.relpath(microservice._combined_main_details["path"], microservice.directory_path)
            grpc_main = microservice._entrypoint_grpc_details["class_name"]
            grpc_path = os.path.relpath(microservice._entrypoint_grpc_details["path"], microservice.directory_path)
            old_main = microservice._old_entrypoint_class.split(".")[-1]
            old_main_path = None
            for file_source, file_path in microservice.file_map.items():
                if file_source.endswith(old_main + ".java"):
                    old_main_path = os.path.relpath(file_path, microservice.directory_path)
                    break
            if not old_main_path:
                microservice.logger.warning(f"Old main class {old_main} not found in microservice {microservice.uid}.")
                old_main_link = old_main
            else:
                old_main_link = f"[{old_main}]({old_main_path})"
            lines.append(f" The microservice has a new main class \"[{combined_main}]({combined_path})\" that combines the "
                         f"old main of the monolith \"{old_main_link}\" and the new gRPC main class \"[{grpc_main}]({grpc_path})\".")
        elif microservice._entrypoint_grpc_details:
            grpc_main = microservice._entrypoint_grpc_details["class_name"]
            grpc_path = os.path.relpath(microservice._entrypoint_grpc_details["path"], microservice.directory_path)
            lines.append(f" The microservice has a new main class \"[{grpc_main}]({grpc_path})\" that exposes the gRPC services.")
        elif microservice._old_entrypoint_class:
            lines.append(f" The microservice has inherited the old main class \"{old_main_link}\" of the monolith.")
        else:
            lines.append(f" The microservice does not have defined a main class.")
        lines.append("")
        ## Changes Section
        lines.append("---\n")
        lines.append("---\n")
        lines.append(f"## Changes")
        lines.append(f" The following changes were made in order to create the microservice:")
        ### Dependencies
        if microservice.dependency_mode:
            lines.append(f"### Dependencies")
            rel_path = os.path.relpath(microservice.dependency_file, microservice.directory_path)
            filename = os.path.basename(microservice.dependency_file)
            lines.append(f" The dependencies of the microservice have been updated. The following packages were added "
                         f"to the file [{filename}]({rel_path}):")
            added_deps = REQUIRED_DEPENDENCIES
            if microservice.dependency_mode in ["client", "both"]:
                added_deps += CLIENT_REQUIRED_DEPENDENCIES
            if microservice.dependency_mode in ["server", "both"]:
                added_deps += SERVER_REQUIRED_DEPENDENCIES
            dep_lines = []
            for dep in added_deps:
                dep_lines.append(f" - `{dep['groupId']}:{dep['artifactId']}:{dep['version']}`")
            dep_lines = list(set(dep_lines))
            dep_lines.sort()
            lines.extend(dep_lines)
            lines.append("")
        ### Copied Classes
        lines.append(f"### Copied Classes")
        lines.append(f" The following classes were copied from the original microservice based on the decomposition:")
        duplicated_classes = [dup[0] for dup in microservice.partition.duplicated_classes]
        for class_name, path in microservice.class_file_map.items():
            if path and (class_name not in duplicated_classes):
                rel_path = os.path.relpath(path, microservice.directory_path)
                lines.append(f" - `{class_name}` was copied to [{rel_path}]({rel_path})")
        lines.append("")
        ### Duplicated Classes
        if n_duplicates:
            lines.append(f"### Duplicated Classes")
            lines.append(f" The following classes were added as duplicates during the preprocessing step of "
                         f"the approach due to reasons such as (parent classes, missing from decomposition):")
            for class_name, original_service in microservice.partition.duplicated_classes:
                if class_name in microservice.class_file_map and microservice.class_file_map[class_name]:
                    rel_path = os.path.relpath(microservice.class_file_map[class_name], microservice.directory_path)
                    original_svc_text = f" (from microservice \"{original_service}\")" if original_service else ""
                    lines.append(f" - `{class_name}` was duplicated {original_svc_text} to "
                                 f"[{rel_path}]({rel_path})")
            lines.append("")
        ### New Services
        if microservice.new_server:
            lines.append(f"### New Services")
            lines.append(f" The following gRPC services were generated and added to expose their corresponding classes "
                         f"to other microservices:")
            for sc, service_details in microservice.new_server.items():
                original_class = service_details["original_class"]
                api_class = api_classes.get(original_class)
                corresponding_proto = None
                proto_rel_path = None
                proto_details = None
                for proto_file, proto_details in microservice._new_proto.items():
                    if proto_details["original_class"] == original_class:
                        corresponding_proto = proto_details["file_name"]
                        proto_rel_path = os.path.relpath(proto_details["path"], microservice.directory_path)
                        break
                rel_path = os.path.relpath(service_details["path"], microservice.directory_path) if "path" in service_details else None
                # service_name = service_details["full_name"]
                service_name = api_class.service_name
                original_class_path = os.path.relpath(microservice.class_file_map[original_class], microservice.directory_path)
                if corresponding_proto:
                    lines.append(f" - Class `{service_name}`:")
                    lines.append(f"   - Exposes the API of [{original_class}]({original_class_path})")
                    if rel_path:
                        lines.append(f"   - Location: [{rel_path}]({rel_path})")
                    lines.append(f"   - Corresponding Proto service `{proto_details['service_name']}` in file "
                                 f"[{corresponding_proto}]({proto_rel_path})")
                    if api_class.decision != ApproachType.ID_BASED and service_details["mapper_path"]:
                        lines.append(f"   - DTO Message: {api_class.dto_name} in [{corresponding_proto}]({proto_rel_path})")
                        mapper_path = os.path.relpath(service_details["mapper_path"], microservice.directory_path)
                        lines.append(f"   - Mapper class: [{api_class.mapper_name}]({mapper_path})")
                else:
                    microservice.logger.warning(f"Proto file for service {service_name} not found.")
            lines.append("")
        ### New Clients
        if microservice._new_client:
            lines.append(f"### New Clients")
            lines.append(f" The following gRPC clients were generated and added to invoke their corresponding "
                         f"servers through RPCs. They serve as proxies to their corresponding original classes:")
            for client_file, client_details in microservice._new_client.items():
                rel_path = os.path.relpath(client_details["path"], microservice.directory_path)
                client_name = client_details["full_name"]
                original_class = client_details["original_class"]
                corresponding_proto = None
                proto_rel_path = None
                proto_details = None
                for proto_file, proto_details in microservice._new_proto.items():
                    if proto_details["original_class"] == original_class:
                        corresponding_proto = proto_details["file_name"]
                        proto_rel_path = os.path.relpath(proto_details["path"], microservice.directory_path)
                        break
                if corresponding_proto:
                    lines.append(f" - Class `{client_name}`:")
                    lines.append(f"   - A proxy for `{original_class}`")
                    lines.append(f"   - Location: [{rel_path}]({rel_path})")
                    lines.append(f"   - Corresponding Proto service `{proto_details['service_name']}` in file "
                                 f"[{corresponding_proto}]({proto_rel_path})")
                    api_class = api_classes[original_class]
                    if api_class.decision != ApproachType.ID_BASED:
                        lines.append(f"   - DTO Message: {api_class.dto_name} in [{corresponding_proto}]({proto_rel_path})")
                else:
                    microservice.logger.warning(f"Proto file for client {client_name} not found.")
            lines.append("")
        ### New Helpers
        if microservice._included_helpers:
            lines.append(f"### Shared Utilities")
            lines.append(f" The following helper classes were added to the microservice in order to implement the "
                         f"pattern and shared logic defined in the approach (leasing, service discovery, ID mapping, etc):")
            for helper, path in microservice._included_helpers.items():
                rel_path = os.path.relpath(path, microservice.directory_path)
                description = microservice.helper_manager.helper_mapping[helper]["description"]
                file_type = "Proto file" if helper.endswith(".proto") else "Class"
                lines.append(f" - Helper {file_type} `{helper}`:")
                lines.append(f"   - Location: [{rel_path}]({rel_path})")
                lines.append(f"   - Description: {description}")
        if microservice._generated_helpers or microservice._entrypoint_grpc_details or microservice._combined_main_details:
            lines.append(f"### Generated Utilities")
            lines.append(f" The following helper classes were generated and customized for the microservice \"{microservice.name}\":")
            for helper, details in microservice._generated_helpers.items():
                path = details[0]
                rel_path = os.path.relpath(path, microservice.directory_path)
                description = microservice.helper_manager.helper_mapping[details[1]]["description"]
                lines.append(f" - Class `{helper}` was generated for the microservice:")
                lines.append(f"   - Location: [{rel_path}]({rel_path})")
                lines.append(f"   - Description: {description}")
            for key, details in [("grpc", microservice._entrypoint_grpc_details),
                                 ("combined", microservice._combined_main_details)]:
                descriptions = {
                    "grpc": "A Server class with a main method that initializes and exposes the new gRPC services",
                    "combined": "A new entrypoint class that combines the old entrypoint of the monolith and "
                                "the new gRPC server class"
                }
                if details:
                    rel_path = os.path.relpath(details["path"], microservice.directory_path)
                    class_name = details["class_name"]
                    description = descriptions[key]
                    is_entrypoint = key == "combined" or microservice._combined_main_details is None
                    lines.append(f" -  Class `{class_name}`:")
                    lines.append(f"     - Location: [{rel_path}]({rel_path})")
                    lines.append(f"     - Description: {description}")
                    if is_entrypoint:
                        lines.append(f"     - **This is the main entrypoint of the microservice**")
            lines.append("")
        ### Updated Imports
        if microservice.import_plan:
            lines.append(f"### Updated Imports")
            lines.append(f" The following imports were updated in the microservice:")
            for target_class, replacements in microservice.import_plan.items():
                rel_path = os.path.relpath(microservice.class_file_map[target_class], microservice.directory_path)
                lines.append(f" - In class [{target_class}]({rel_path}):")
                for old_class, new_class in replacements.items():
                    lines.append(f"   - `{old_class}` was replaced with `{new_class}`")
            lines.append("")
        ## Detailed Refactoring Comments
        lines.append("---\n")
        if microservice.new_server:
            lines.append("---\n")
            lines.append(f"## Detailed Refactoring Comments for Exposed Services")
            for sc, service_details in microservice.new_server.items():
                corresponding_proto_details = None
                for proto_file, proto_details in microservice._new_proto.items():
                    if proto_details["original_class"] == service_details["original_class"]:
                        corresponding_proto_details = proto_details
                if not corresponding_proto_details:
                    microservice.logger.warning(f"Proto file for the service corresponding to "
                                                f"{service_details['original_class']} not found.")
                    continue
                lines.append(f"### Original Class `{service_details['original_class']}`")
                service_name = api_classes[service_details["original_class"]].service_name
                lines.append(f"#### Service `{service_name}`")
                lines.append(f"##### Explanation")
                context = f" in {microservice.uid}/{corresponding_proto_details['file_name']}"
                explanation, comments = self.cleanup_explanation_comments(corresponding_proto_details["explanation"],
                                                                          corresponding_proto_details["comments"],
                                                                          context)
                lines.append(f" {explanation}")
                lines.append(f"##### Comments")
                lines.append(f" {comments}")
                if "full_name" not in service_details:
                    lines.append("\n---\n")
                    continue
                lines.append(f"#### Server Class `{service_details['full_name']}`")
                context = f" in {microservice.uid}/{service_details['file_name']}"
                explanation, comments = self.cleanup_explanation_comments(service_details["explanation"],
                                                                          service_details["comments"],
                                                                          context)
                lines.append(f"##### Explanation")
                lines.append(f" {explanation}")
                lines.append(f"##### Comments")
                lines.append(f" {comments}")
                lines.append("\n---\n")
            lines.append("")
        if microservice._new_client:
            lines.append("---\n")
            lines.append(f"## Detailed Refactoring Comments for Consumed Services")
            for client_file, client_details in microservice._new_client.items():
                corresponding_proto_details = None
                for proto_file, proto_details in microservice._new_proto.items():
                    if proto_details["original_class"] == client_details["original_class"]:
                        corresponding_proto_details = proto_details
                if not corresponding_proto_details:
                    microservice.logger.warning(f"Proto file for service {client_details['full_name']} not found.")
                    continue
                lines.append(f"### Original Class `{client_details['original_class']}`")
                lines.append(f"#### Client Class `{client_details['full_name']}` "
                             f"(Service `{corresponding_proto_details['service_name']}`)")
                context = f" in {microservice.uid}/{client_details['file_name']}"
                explanation, comments = self.cleanup_explanation_comments(client_details["explanation"],
                                                                          client_details["comments"],
                                                                          context)
                lines.append(f"##### Explanation")
                lines.append(f" {explanation}")
                lines.append(f"##### Comments")
                lines.append(f" {comments}")
                lines.append("\n---\n")
            lines.append("---\n")

        report_path = os.path.join(microservice.directory_path, "REFACTORING_REPORT.md")
        microservice.logger.debug(f"Writing microservice {microservice.uid} report to {report_path}")
        with open(report_path, "w") as f:
            f.write("\n".join(lines))
            
    def cleanup_explanation_comments(self, explanation: str, comments: str, context: str = "") -> tuple[str, str]:
        pattern = re.compile(r"#+\s*([^\n]*)\n?", re.MULTILINE)
        replacement = r"  **\1**\n"
        explanation = explanation.replace(comments, "")
        explanation = re.sub(r"#+\s*Comments", "", explanation)
        comments = re.sub(r"#+\s*Comments", "", comments)
        explanation = re.sub(pattern, replacement, explanation)
        comments = re.sub(pattern, replacement, comments)
        # if re.match(r"```([^`]*\n)*[^`]*$", explanation):
        n_blocks = explanation.count("```")
        if n_blocks > -1 and n_blocks % 2 != 0:
            self.logger.debug(f"Adding code block to explanation{context}")
            explanation += "```"
        # if re.match(r"```([^`]*\n)*[^`]*$", comments):
        n_blocks = comments.count("```")
        if n_blocks > -1 and n_blocks % 2 != 0:
            self.logger.debug(f"Adding code block to comments{context}")
            comments += "```"
        # explanation = re.sub(r"```(([^`]*\n)*[^`]*)```", "", explanation)
        # comments = re.sub(r"```(([^`]*\n)*[^`]*)```", "", comments)
        return explanation, comments