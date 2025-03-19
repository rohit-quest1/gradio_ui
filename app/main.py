import json
import asyncio
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import gradio as gr
from app.ui.chat_ui import ChatUI
from app.services.memcached_service import validate_memcached_connection, profile_memcached
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import matplotlib.pyplot as plt
import os

# Initialize FastAPI app and logger
app = FastAPI()
app.mount("/charts", StaticFiles(directory="./app/output/charts", html=True), name="charts")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_gradio_interface():
    chat_ui = ChatUI()
    
    with gr.Blocks(theme=gr.themes.Default(font=[gr.themes.GoogleFont("Inconsolata"), "Arial", "sans-serif"])) as interface:
        gr.Markdown("# Quester - Redis Migration Assessment Tool")
        
        with gr.Row():
            with gr.Column(scale=2):
                # Chat Tab
                chatbot = gr.Chatbot(
                    label="Redis Migration Assessment",
                    render=True,
                    height=600
                )
                msg = gr.Textbox(
                    label="Your Response",
                    placeholder="Type your response here..."
                )
                clear = gr.Button("Start Over")
            
            with gr.Column(scale=1):
                # Dynamic options area
                options_container = gr.Group(visible=False)
                with options_container:
                    question_header = gr.Markdown("### Question")
                    
                    # For single select questions
                    single_select_container = gr.Group(visible=False)
                    with single_select_container:
                        single_select = gr.Radio(
                            choices=[],
                            label="Select one option",
                            interactive=True
                        )
                        submit_single = gr.Button("Submit Selection")
                    
                    # For multi select questions
                    multi_select_container = gr.Group(visible=False)
                    with multi_select_container:
                        multi_select = gr.CheckboxGroup(
                            choices=[],
                            label="Select all that apply",
                            interactive=True
                        )
                        submit_multi = gr.Button("Submit Selections")
        
        # Function to handle initial URL input and show first question
        async def initial_response(message, chat_history):
            result = await chat_ui.handle_url_input(message)
            chat_history.append((message, result))
            
            if not chat_ui.is_url_validated:
                return chat_history, "", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(), gr.update(choices=[]), gr.update(choices=[])
            
            # Get first question
            section, subsection = chat_ui.get_current_question()
            if section and subsection:
                question_text = f"### {section['name']}\n#### {subsection['name']}"
                chat_history.append((None, f"Please select an option from the panel on the right."))
                
                # Update options based on question type
                if "isMultiSelect" in subsection and subsection["isMultiSelect"]:
                    return (
                        chat_history, 
                        "", 
                        gr.update(visible=True),  # options_container 
                        gr.update(visible=False),  # single_select_container
                        gr.update(visible=True),  # multi_select_container
                        gr.update(value=question_text),  # question_header
                        gr.update(value=None, choices=[]),  # single_select - clear choices
                        gr.update(value=[], choices=subsection["options"])  # multi_select - set new choices
                    )
                else:
                    return (
                        chat_history, 
                        "", 
                        gr.update(visible=True),  # options_container
                        gr.update(visible=True),  # single_select_container
                        gr.update(visible=False),  # multi_select_container
                        gr.update(value=question_text),  # question_header
                        gr.update(value=None, choices=subsection["options"]),  # single_select - set new choices
                        gr.update(value=[], choices=[])  # multi_select - clear choices
                    )
            
            return chat_history, "", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(), gr.update(choices=[]), gr.update(choices=[])
        
        # Function to handle single selection submission
        async def submit_single_selection(selection, chat_history):
            if not selection:
                return chat_history, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
            
            section, subsection = chat_ui.get_current_question()
            if not section or not subsection:
                return chat_history, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
            
            # Process the selection
            key = f"{section['name']}_{subsection['name']}"
            chat_ui.responses[key] = selection
            
            # Add to chat history
            chat_history.append((f"Selected: {selection}", None))
            
            # Move to next question
            if chat_ui.current_subsection + 1 < len(section["subSections"]):
                chat_ui.current_subsection += 1
            else:
                chat_ui.current_section += 1
                chat_ui.current_subsection = 0
            
            # Get next question
            new_section, new_subsection = chat_ui.get_current_question()
            if new_section and new_subsection:
                question_text = f"### {new_section['name']}\n#### {new_subsection['name']}"
                chat_history.append((None, f"Please select an option from the panel on the right."))
                
                # Update options based on question type
                if "isMultiSelect" in new_subsection and new_subsection["isMultiSelect"]:
                    return (
                        chat_history,
                        gr.update(visible=True),  # options_container 
                        gr.update(visible=False),  # single_select_container
                        gr.update(visible=True),  # multi_select_container
                        gr.update(value=question_text),  # question_header
                        gr.update(value=None, choices=[]),  # single_select - clear previous choices
                        gr.update(value=[], choices=new_subsection["options"])  # multi_select - set new choices
                    )
                else:
                    return (
                        chat_history,
                        gr.update(visible=True),  # options_container
                        gr.update(visible=True),  # single_select_container
                        gr.update(visible=False),  # multi_select_container
                        gr.update(value=question_text),  # question_header
                        gr.update(value=None, choices=new_subsection["options"]),  # single_select - set new choices
                        gr.update(value=[], choices=[])  # multi_select - clear previous choices
                    )
            else:
                # Generate final report
                report = await chat_ui.generate_final_report(chat_history)
                return report, gr.update(visible=False), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        
        # Function to handle multi selection submission
        async def submit_multi_selection(selections, chat_history):
            if not selections:
                return chat_history, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
            
            section, subsection = chat_ui.get_current_question()
            if not section or not subsection:
                return chat_history, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
            
            # Process the selections
            key = f"{section['name']}_{subsection['name']}"
            chat_ui.responses[key] = selections
            
            # Add to chat history
            chat_history.append((f"Selected: {', '.join(selections)}", None))
            
            # Move to next question
            if chat_ui.current_subsection + 1 < len(section["subSections"]):
                chat_ui.current_subsection += 1
            else:
                chat_ui.current_section += 1
                chat_ui.current_subsection = 0
            
            # Get next question
            new_section, new_subsection = chat_ui.get_current_question()
            if new_section and new_subsection:
                question_text = f"### {new_section['name']}\n#### {new_subsection['name']}"
                chat_history.append((None, f"Please select an option from the panel on the right."))
                
                # Update options based on question type
                if "isMultiSelect" in new_subsection and new_subsection["isMultiSelect"]:
                    return (
                        chat_history,
                        gr.update(visible=True),  # options_container 
                        gr.update(visible=False),  # single_select_container
                        gr.update(visible=True),  # multi_select_container
                        gr.update(value=question_text),  # question_header
                        gr.update(value=None, choices=[]),  # single_select - clear previous choices
                        gr.update(value=[], choices=new_subsection["options"])  # multi_select - set new choices
                    )
                else:
                    return (
                        chat_history,
                        gr.update(visible=True),  # options_container
                        gr.update(visible=True),  # single_select_container
                        gr.update(visible=False),  # multi_select_container
                        gr.update(value=question_text),  # question_header
                        gr.update(value=None, choices=new_subsection["options"]),  # single_select - set new choices
                        gr.update(value=[], choices=[])  # multi_select - clear previous choices
                    )
            else:
                # Generate final report
                report = await chat_ui.generate_final_report(chat_history)
                return report, gr.update(visible=False), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        
        # Reset function
        def reset():
            chat_history = [(None, chat_ui.welcome_message)]
            chat_ui.reset()
            return (
                chat_history, 
                gr.update(visible=False),  # options_container
                gr.update(visible=False),  # single_select_container
                gr.update(visible=False),  # multi_select_container
                gr.update(value=""),  # question_header
                gr.update(choices=[]),  # single_select
                gr.update(choices=[])  # multi_select
            )
        
        # Connect event handlers
        msg.submit(
            initial_response,
            [msg, chatbot],
            [chatbot, msg, options_container, single_select_container, multi_select_container, 
             question_header, single_select, multi_select]
        )
        
        submit_single.click(
            submit_single_selection,
            [single_select, chatbot],
            [chatbot, options_container, single_select_container, multi_select_container, 
             question_header, single_select, multi_select]
        )
        
        submit_multi.click(
            submit_multi_selection,
            [multi_select, chatbot],
            [chatbot, options_container, single_select_container, multi_select_container, 
             question_header, single_select, multi_select]
        )
        
        clear.click(
            reset,
            [],
            [chatbot, options_container, single_select_container, multi_select_container, 
             question_header, single_select, multi_select]
        )
        
        interface.load(
            lambda: [(None, chat_ui.welcome_message)],
            outputs=[chatbot]
        )
    
    return interface

# Mount Gradio interface
app = gr.mount_gradio_app(app, create_gradio_interface(), path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)