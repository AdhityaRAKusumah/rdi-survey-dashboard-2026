import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import folium
import re
from streamlit_folium import folium_static
from translation import translate_display_text
from ui_theme import DEEP_BLUE, INK, MUTED, PLOTLY_COLORWAY, SURFACE

DEFAULT_CHART_HEIGHT = 580
DEFAULT_PIE_HEIGHT = 560
MAX_CATEGORIES = 10

class ChartGenerator:
    """
    A class to generate various types of charts for the Biogas Survey Dashboard.
    This centralizes chart creation functionality to make the main app cleaner.
    """
    
    def __init__(self, data):
        """
        Initialize the ChartGenerator with a DataFrame.
        
        Args:
            data (pandas.DataFrame): The DataFrame to use for chart generation.
        """
        self.data = data
    
    def update_data(self, data):
        """
        Update the DataFrame used for chart generation.
        
        Args:
            data (pandas.DataFrame): The new DataFrame to use.
        """
        self.data = data

    def _resolve_column_ref(self, column_ref):
        if isinstance(column_ref, int):
            index_map = self.data.attrs.get("old_index_to_new_column", {})
            if column_ref in index_map and index_map[column_ref] in self.data.columns:
                return index_map[column_ref]
            if 0 <= column_ref < len(self.data.columns):
                return self.data.columns[column_ref]
            return None
        return column_ref

    def _empty_chart(self, title, message="Data column is not available in the current workbook."):
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=14, color=MUTED),
        )
        fig.update_layout(
            title={"text": self._wrap_title(title), "x": 0.02, "xanchor": "left"},
            meta={"empty_chart": True, "empty_reason": message},
        )
        return self._apply_theme(fig)

    def _apply_theme(self, fig):
        """
        Apply the Biru Karbon Nusantara visual system to Plotly figures.
        """
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor=SURFACE,
            plot_bgcolor="#F8FBFF",
            height=fig.layout.height or DEFAULT_CHART_HEIGHT,
            colorway=PLOTLY_COLORWAY,
            font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
            title=dict(
                font=dict(size=17, color=DEEP_BLUE, family='Inter, "Segoe UI", Arial, sans-serif'),
                x=0.02,
                xanchor="left",
                y=0.98,
                yanchor="top",
            ),
            margin=dict(l=70, r=42, t=148, b=86),
            legend=dict(
                bgcolor="rgba(255,255,255,0)",
                borderwidth=0,
                font=dict(color=INK, size=12),
                title=dict(font=dict(color=MUTED, size=12)),
            ),
            hoverlabel=dict(
                bgcolor=DEEP_BLUE,
                bordercolor=DEEP_BLUE,
                font=dict(color="#FFFFFF", family='Inter, "Segoe UI", Arial, sans-serif'),
            ),
        )
        fig.update_xaxes(
            showgrid=True,
            gridcolor="rgba(24, 79, 143, 0.08)",
            zeroline=False,
            linecolor="rgba(20, 36, 58, 0.15)",
            tickfont=dict(color=MUTED),
            title_font=dict(color=INK),
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor="rgba(24, 79, 143, 0.08)",
            zeroline=False,
            linecolor="rgba(20, 36, 58, 0.15)",
            tickfont=dict(color=MUTED),
            title_font=dict(color=INK),
        )

        for idx, trace in enumerate(fig.data):
            color = PLOTLY_COLORWAY[idx % len(PLOTLY_COLORWAY)]
            if getattr(trace, "type", None) == "pie":
                labels = getattr(trace, "labels", None)
                color_count = len(labels) if labels is not None else len(PLOTLY_COLORWAY)
                trace.update(
                    marker=dict(
                        colors=[PLOTLY_COLORWAY[i % len(PLOTLY_COLORWAY)] for i in range(color_count)],
                        line=dict(color="#FFFFFF", width=2),
                    ),
                    textfont=dict(color="#FFFFFF", size=13),
                    domain=dict(x=[0.05, 0.95], y=[0.0, 0.9]),
                )
            elif getattr(trace, "type", None) in {"bar", "histogram"}:
                trace.update(marker=dict(color=color, line=dict(color="rgba(255,255,255,0.65)", width=1)))
            elif getattr(trace, "type", None) in {"scatter", "scattergl"}:
                trace.update(line=dict(color=color, width=2.7), marker=dict(color=color, size=8))

        fig.update_layout(
            uniformtext_minsize=10,
            uniformtext_mode="hide",
        )
        fig.update_xaxes(automargin=True)
        fig.update_yaxes(automargin=True)
        return fig
    
    def _wrap_title(self, title, max_length=52):
        """
        Helper method to wrap long titles to multiple lines.
        
        Args:
            title (str): The title to wrap
            max_length (int): Maximum characters per line
            
        Returns:
            str: Title with line breaks inserted if needed
        """
        if not title or len(title) <= max_length:
            return title
            
        # Find a good place to break the title (at a space)
        words = title.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            # If adding this word would exceed the max length and we already have words
            if current_length + len(word) + (1 if current_length > 0 else 0) > max_length and current_line:
                # Add the current line to lines and start a new line
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
            else:
                # Add the word to the current line
                current_line.append(word)
                # Add word length + space
                current_length += len(word) + (1 if current_length > 0 else 0)
        
        # Add the last line if it's not empty
        if current_line:
            lines.append(' '.join(current_line))
        
        # Join the lines with <br> for plotly
        return '<br>'.join(lines)

    def _shorten_axis_label(self, value, max_length=38):
        text = self._clean_category_label(value)
        if pd.isna(text):
            return text
        text = str(text).strip()
        compact_map = {
            "Yes, Stove Type Changed": "Stove Changed",
            "No, Stove Type Remains The Same": "No Change",
            "Forest/Garden Firewood Is More Available And Easier To Obtain": "Firewood Easier To Obtain",
            "Forest/Garden Firewood Is Cheaper": "Cheaper Forest Firewood",
            "Fuel Is Easier To Obtain Nearby": "Fuel Easier To Obtain",
            "Fuel Is More Affordable/Cheaper": "Fuel Is Cheaper",
            "Household Members Increased": "Household Increased",
            "More Stoves Used At The Same Time": "More Stoves Used",
            "Cooking Needs Increased": "Cooking Needs Increased",
            "Free Assistance": "Free Assistance",
            "Curious About Biogas": "Curious About Biogas",
            "Use Of Cattle Manure": "Cattle Manure Use",
            "Use Of Bio-slurry": "Bio-slurry Use",
            "No Operator": "No Operator",
            "Layout Constraint": "Layout Constraint",
            "House Renovation / Shed Moved": "House/Shed Renovation",
            "Project PE Does Not Meet Standard": "PE Standard Issue",
        }
        for phrase, short in compact_map.items():
            if text.startswith(phrase) or phrase in text:
                return short
        return text if len(text) <= max_length else text[: max_length - 1].rstrip() + "..."

    def _use_display_category(self, chart_data, category_col, max_length=38):
        display_col = f"_{category_col}_display"
        chart_data = chart_data.copy()
        chart_data[display_col] = chart_data[category_col].apply(lambda value: self._shorten_axis_label(value, max_length=max_length))
        return chart_data, display_col

    def _clean_category_label(self, value):
        if pd.isna(value):
            return np.nan
        text = str(value).strip()
        if not text:
            return np.nan
        lowered = text.lower().strip(" .,-")
        if lowered in {"nan", "none", "null", "0", "0.0", "1", "1.0"}:
            return np.nan

        replacements = {
            "istirahat": "Rest/Relaxation",
            "santai": "Rest/Relaxation",
            "capek": "Rest/Relaxation",
            "lelah": "Rest/Relaxation",
            "tidak ada waktu": "No Saved/Free Time",
            "waktu yang dihemat": "No Saved/Free Time",
            "waktu luang": "No Saved/Free Time",
            "kumpul keluarga": "Family Time",
            "bersama keluarga": "Family Time",
            "pengajian": "Religious Gathering",
            "pkk": "PKK",
            "pertemuan rt": "Neighborhood Meeting",
            "arisan": "Community Savings Gathering",
            "gotong": "Community Work",
            "berkebun": "Gardening/Farming",
            "bertani": "Gardening/Farming",
            "tani": "Gardening/Farming",
            "berjualan": "Selling/Trading",
            "berdagang": "Selling/Trading",
        }
        for needle, replacement in replacements.items():
            if needle in lowered:
                return replacement

        text = re.sub(r"\s+", " ", text.replace("_", " "))
        if text.isupper() or text.islower():
            text = text.title()
        else:
            words = []
            for word in text.split(" "):
                words.append(word if any(ch.isupper() for ch in word[1:]) else word.capitalize())
            text = " ".join(words)
        acronym_map = {
            "Diy": "DIY",
            "Ntb": "NTB",
            "Ntt": "NTT",
            "Lpg": "LPG",
            "Cpo": "CPO",
            "Biru": "BIRU",
            "Pkk": "PKK",
            "Rt": "RT",
            "Rw": "RW",
        }
        for source, target in acronym_map.items():
            text = re.sub(rf"\b{source}\b", target, text)
        return translate_display_text(text)

    def _shorten_legend_label(self, value, max_length=30):
        text = self._clean_category_label(value)
        if pd.isna(text):
            return text
        replacements = {
            "No Change": "No Change",
            "Much Better": "Much Better",
            "Better": "Better",
            "Worse": "Worse",
            "Do Not Know": "Do Not Know",
            "Know": "Know",
            "No, Did Not Receive Instructions": "No Instructions",
            "Yes, Very Clear And Easy To Follow": "Very Clear",
            "Yes, Clear Enough And Easy To Follow": "Clear Enough",
            "Yes, But Less Clear And Difficult To Follow": "Less Clear",
            "Yes, But The Instructions Were Not Clear": "Not Clear",
        }
        for phrase, short in replacements.items():
            if text.startswith(phrase):
                return short
        return text if len(text) <= max_length else text[: max_length - 1].rstrip() + "..."

    def _clean_category_columns(self, data, columns):
        clean_data = data.copy()
        for column in columns:
            if column in clean_data.columns:
                clean_data[column] = clean_data[column].apply(self._clean_category_label)
        return clean_data

    def _limit_categories(self, chart_data, category_col, value_col, max_categories=MAX_CATEGORIES):
        if category_col not in chart_data.columns or value_col not in chart_data.columns:
            return chart_data
        if chart_data[category_col].nunique(dropna=True) <= max_categories:
            return chart_data

        totals = chart_data.groupby(category_col, dropna=True)[value_col].sum().sort_values(ascending=False)
        top_categories = set(totals.head(max_categories).index)
        limited = chart_data.copy()
        limited[category_col] = limited[category_col].where(limited[category_col].isin(top_categories), "Other")
        group_cols = [col for col in limited.columns if col != value_col]
        return limited.groupby(group_cols, dropna=False, as_index=False)[value_col].sum()

    def _truthy_selection_count(self, series):
        cleaned = series.dropna().astype(str).str.strip().str.lower()
        selected = cleaned[~cleaned.isin(["", "0", "0.0", "false", "no", "tidak", "nan", "none"])]
        return int(selected.shape[0])

    def _coerce_numeric_series(self, series):
        def parse_value(value):
            if pd.isna(value):
                return np.nan
            if isinstance(value, (int, float, np.integer, np.floating)):
                return value
            if isinstance(value, (pd.Timestamp, np.datetime64)):
                return np.nan

            text = str(value).strip()
            lowered = text.lower()
            if lowered in {"", "nan", "none", "null"}:
                return np.nan
            if "tidak ada perubahan" in lowered:
                return 0
            if re.search(r"\d{4}-\d{1,2}-\d{1,2}", lowered):
                return np.nan

            direct_value = pd.to_numeric(text, errors='coerce')
            if not pd.isna(direct_value):
                return direct_value

            cleaned = lowered.replace("rp", "").replace("idr", "")
            numbers = re.findall(r"\d+(?:[.,]\d+)*", cleaned)
            parsed_numbers = []
            for number in numbers:
                normalized = number.replace(".", "").replace(",", "")
                parsed_value = pd.to_numeric(normalized, errors='coerce')
                if not pd.isna(parsed_value):
                    parsed_numbers.append(float(parsed_value))

            if len(parsed_numbers) >= 2 and "-" in cleaned:
                return sum(parsed_numbers[:2]) / 2
            if parsed_numbers:
                return parsed_numbers[0]

            return np.nan

        return series.apply(parse_value)
    
    def _aggregate_data(self, x_col, y_col, agg_method="count", group_col=None):
        """
        Aggregates data based on specified columns and method.
        
        Args:
            x_col (str): Column for x-axis
            y_col (str): Column for y-axis (used for values)
            agg_method (str): Aggregation method ('count', 'sum', 'mean', 'median', 'min', 'max', 'count_unique')
            group_col (str, optional): Column to group by (for multi-series charts)
            
        Returns:
            pandas.DataFrame: Aggregated data
        """
        # Convert data to proper types if needed (e.g., datetime)
        data_copy = self.data.copy()
        
        # Try to convert to datetime if 'date' or 'year' in column name
        if x_col and ('date' in x_col.lower() or 'year' in x_col.lower() or 'time' in x_col.lower()):
            try:
                data_copy[x_col] = pd.to_datetime(data_copy[x_col])
                # Extract year if it's datetime
                if 'year' in x_col.lower() and data_copy[x_col].dtype == 'datetime64[ns]':
                    data_copy[x_col] = data_copy[x_col].dt.year
            except:
                # If conversion fails, keep as is
                pass
        
        # Define groupby columns
        groupby_cols = [x_col] if x_col else []
        if group_col and group_col != "None":
            groupby_cols.append(group_col)
            
        # Skip aggregation if no groupby columns
        if not groupby_cols:
            return data_copy
            
        # Aggregation logic
        if agg_method == "count":
            # For count, simply count rows in each group
            agg_data = data_copy.groupby(groupby_cols).size().reset_index(name='count')
            result_y_col = 'count'
        elif agg_method == "count_unique":
            # Count unique values
            if y_col:
                agg_data = data_copy.groupby(groupby_cols)[y_col].nunique().reset_index(name='count_unique')
                result_y_col = 'count_unique'
            else:
                # If no y_col provided, fall back to regular count
                agg_data = data_copy.groupby(groupby_cols).size().reset_index(name='count')
                result_y_col = 'count'
        else:
            # For other aggregations, apply to y_col
            if y_col:
                data_copy[y_col] = self._coerce_numeric_series(data_copy[y_col])
                agg_func = {
                    "sum": "sum",
                    "mean": "mean",
                    "median": "median",
                    "min": "min",
                    "max": "max"
                }.get(agg_method, "mean")  # Default to mean if unknown
                
                agg_data = data_copy.groupby(groupby_cols)[y_col].agg(agg_func).reset_index()
                result_y_col = y_col
            else:
                # If no y_col provided, fall back to count
                agg_data = data_copy.groupby(groupby_cols).size().reset_index(name='count')
                result_y_col = 'count'
                
        return agg_data, result_y_col
    
    def create_bar_chart(self, x_col, y_col=None, agg_method="count", title="Bar Chart", 
                         x_label=None, y_label=None, color=None, legend_title=None, orientation="v", height=None):
        """
        Create a bar chart using Plotly.
        
        Args:
            x_col (str): Column name for x-axis.
            y_col (str, optional): Column name for y-axis values. If None, counts are used.
            agg_method (str): Aggregation method ('count', 'sum', 'mean', 'median', 'min', 'max', 'count_unique')
            title (str, optional): Chart title.
            x_label (str, optional): X-axis label. Defaults to x_col if None.
            y_label (str, optional): Y-axis label. Defaults to y_col or agg_method if None.
            color (str, optional): Column name for color encoding.
            legend_title (str, optional): Custom title for the legend. Defaults to color column name.
            orientation (str, optional): Bar orientation ('v' for vertical, 'h' for horizontal).
            height (int, optional): Height of the chart in pixels.
        
        Returns:
            plotly.graph_objects.Figure: The created bar chart.
        """
        x_col = self._resolve_column_ref(x_col)
        
        color = self._resolve_column_ref(color)
        if not x_col or x_col not in self.data.columns:
            return self._empty_chart(title)
        if color and color not in self.data.columns:
            color = None

        clean_columns = [x_col]
        if color:
            clean_columns.append(color)
        source_data = self._clean_category_columns(self.data, clean_columns)
        original_data = self.data
        self.data = source_data
        agg_result = self._aggregate_data(x_col, y_col, agg_method, color)
        self.data = original_data
        if isinstance(agg_result, tuple):
            chart_data, result_y_col = agg_result
        else:
            chart_data, result_y_col = agg_result, y_col if y_col else 'count'

        chart_data = chart_data.dropna(subset=[x_col])
        chart_data = self._limit_categories(chart_data, x_col, result_y_col)
        chart_data, display_x_col = self._use_display_category(chart_data, x_col, max_length=36)
        if orientation == "v":
            categories = chart_data[display_x_col].dropna().astype(str)
            if categories.nunique() > 6 or (not categories.empty and categories.str.len().mean() > 18):
                orientation = "h"
        
        # Set default labels
        if not x_label:
            x_label = x_col
        if not y_label:
            if y_col:
                y_label = f"{agg_method.capitalize()} of {y_col}"
            else:
                y_label = "Count"
        
        # Create the chart based on orientation
        if orientation == "v":
            fig = px.bar(
                chart_data, 
                x=display_x_col, 
                y=result_y_col, 
                title=title,
                color=color,
                labels={
                    display_x_col: x_label,
                    result_y_col: y_label
                },
                height=height or DEFAULT_CHART_HEIGHT,
                hover_data={x_col: True, display_x_col: False},
            )
        else:
            chart_data = chart_data.sort_values(result_y_col, ascending=True)
            fig = px.bar(
                chart_data, 
                x=result_y_col, 
                y=display_x_col, 
                title=title,
                color=color,
                labels={
                    result_y_col: y_label,
                    display_x_col: x_label
                },
                orientation='h',
                height=height or max(DEFAULT_CHART_HEIGHT, 42 * max(len(chart_data), 8)),
                hover_data={x_col: True, display_x_col: False},
            )
        
        # Update layout
        fig.update_layout(
            title={
                'text': self._wrap_title(title),
                'y':0.98,
                'x':0.02,
                'xanchor': 'left',
                'yanchor': 'top'
            },
            legend_title_text=legend_title if legend_title is not None else (color if color else None)
        )
        
        # Add value labels on top of each bar
        # When color is used, we need to add annotations for the total values
        if color:
            # Get the data used for the chart
            chart_df = chart_data.copy()
            
            # Calculate totals for each x category
            if orientation == "v":
                totals = chart_df.groupby(display_x_col)[result_y_col].sum().reset_index()
                
                # Add annotations for each x category
                annotations = []
                for i, row in totals.iterrows():
                    annotations.append(dict(
                        x=row[display_x_col],
                        y=row[result_y_col],
                        text=f"{row[result_y_col]:.0f}",
                        showarrow=False,
                        yshift=10,  # Adjust this value to position text above the bars
                        font=dict(size=10)
                    ))
                
                fig.update_layout(annotations=annotations)
            else:
                # For horizontal bars
                totals = chart_df.groupby(display_x_col)[result_y_col].sum().reset_index()
                
                # Add annotations for each x category
                annotations = []
                for i, row in totals.iterrows():
                    annotations.append(dict(
                        y=row[display_x_col],
                        x=row[result_y_col],
                        text=f"{row[result_y_col]:.0f}",
                        showarrow=False,
                        xshift=10,  # Adjust this value to position text to the right of the bars
                        font=dict(size=10)
                    ))
                
                fig.update_layout(annotations=annotations)
        else:
            # When no color is used, we can use the simpler approach
            if orientation == "v":
                fig.update_traces(
                    texttemplate='%{y:.0f}',
                    textposition='outside',
                    textfont=dict(size=10)
                )
            else:
                fig.update_traces(
                    texttemplate='%{x:.0f}',
                    textposition='outside',
                    textfont=dict(size=10)
                )
        
        return self._apply_theme(fig)
    
    def create_stacked_bar_chart(self, x_col, y_col=None, stack_col=None, agg_method="count", 
                                title="Stacked Bar Chart", x_label=None, y_label=None, legend_title=None,
                                percentage=False, orientation="v", height=None):
        """
        Create a stacked bar chart using Plotly, with option for 100% stacking.
        
        Args:
            x_col (str): Column name for x-axis.
            y_col (str, optional): Column name for y-axis value. If None, counts are used.
            stack_col (str): Column name for stacking.
            agg_method (str): Aggregation method ('count', 'sum', 'mean', 'median', 'min', 'max', 'count_unique')
            title (str, optional): Chart title.
            x_label (str, optional): X-axis label. Defaults to x_col if None.
            y_label (str, optional): Y-axis label. Defaults to y_col or agg_method if None.
            legend_title (str, optional): Custom title for the legend. Defaults to stack_col name.
            percentage (bool, optional): If True, creates a 100% stacked bar chart.
            orientation (str, optional): Bar orientation ('v' for vertical, 'h' for horizontal).
            height (int, optional): Height of the chart in pixels.
        
        Returns:
            plotly.graph_objects.Figure: The created stacked bar chart.
        """
        x_col = self._resolve_column_ref(x_col)
        y_col = self._resolve_column_ref(y_col)
        stack_col = self._resolve_column_ref(stack_col)
        clean_columns = [col for col in [x_col, stack_col] if col]
        source_data = self._clean_category_columns(self.data, clean_columns)
        original_data = self.data
        self.data = source_data
        if x_col not in self.data.columns:
            self.data = original_data
            return self._empty_chart(title)
        if stack_col and stack_col not in self.data.columns:
            stack_col = None
        agg_result = self._aggregate_data(x_col, y_col, agg_method, stack_col)
        self.data = original_data
        if isinstance(agg_result, tuple):
            chart_data, result_y_col = agg_result
        else:
            chart_data, result_y_col = agg_result, y_col if y_col else 'count'
        if x_col in chart_data.columns:
            chart_data, display_x_col = self._use_display_category(chart_data, x_col, max_length=36)
        else:
            display_x_col = x_col
        
        # Set default labels
        if not x_label:
            x_label = x_col
        if not y_label:
            if y_col:
                y_label = f"{agg_method.capitalize()} of {y_col}"
            else:
                y_label = "Count"
        
        if percentage:
            # For 100% stacked bar chart, we need to calculate percentages
            if orientation == "v":
                # Calculate total for each x category
                totals = chart_data.groupby(x_col)[result_y_col].transform('sum')
                
                # Calculate percentages
                chart_data[result_y_col] = chart_data[result_y_col] / totals
                
                fig = px.bar(
                    chart_data, 
                    x=display_x_col, 
                    y=result_y_col, 
                    color=stack_col,
                    title=title,
                    labels={
                        display_x_col: x_label,
                        result_y_col: y_label
                    },
                    height=height or DEFAULT_CHART_HEIGHT
                )
                
                fig.update_layout(
                    yaxis=dict(
                        tickformat=',.0%',
                        range=[0, 1]  # Set y-axis range from 0 to 1 (0% to 100%)
                    )
                )
            else:
                # Similar logic for horizontal orientation
                totals = chart_data.groupby(display_x_col)[result_y_col].transform('sum')
                chart_data[result_y_col] = chart_data[result_y_col] / totals
                
                fig = px.bar(
                    chart_data, 
                    x=result_y_col, 
                    y=display_x_col, 
                    color=stack_col,
                    title=title,
                    labels={
                        result_y_col: y_label,
                        display_x_col: x_label
                    },
                    orientation='h',
                    height=height or DEFAULT_CHART_HEIGHT
                )
                
                fig.update_layout(
                    xaxis=dict(
                        tickformat=',.0%',
                        range=[0, 1]  # Set x-axis range from 0 to 1 (0% to 100%)
                    )
                )
        else:
            # Regular stacked bar chart
            if orientation == "v":
                fig = px.bar(
                    chart_data, 
                    x=display_x_col, 
                    y=result_y_col, 
                    color=stack_col,
                    title=title,
                    labels={
                        display_x_col: x_label,
                        result_y_col: y_label
                    },
                    height=height or DEFAULT_CHART_HEIGHT,
                    barmode="group"
                )
            else:
                fig = px.bar(
                    chart_data, 
                    x=result_y_col, 
                    y=display_x_col, 
                    color=stack_col,
                    title=title,
                    labels={
                        result_y_col: y_label,
                        display_x_col: x_label
                    },
                    orientation='h',
                    height=height or DEFAULT_CHART_HEIGHT,
                    barmode="group"
                )
        
        fig.update_layout(
            title={
                'text': self._wrap_title(title),
                'y':0.98,
                'x':0.02,
                'xanchor': 'left',
                'yanchor': 'top'
            },
            barmode='relative' if percentage else 'stack',
            legend_title_text=legend_title if legend_title is not None else stack_col
        )
        
        return self._apply_theme(fig)
    
    def create_pie_chart(self, values_col=None, names_col=None, agg_method="count", title="Pie Chart", height=None):
        """
        Create a pie chart using Plotly.
        
        Args:
            values_col (str, optional): Column name for pie slice values. If None, counts are used.
            names_col (str): Column name for pie slice names.
            agg_method (str): Aggregation method ('count', 'sum', 'mean', 'median', 'min', 'max', 'count_unique')
            title (str, optional): Chart title.
            height (int, optional): Height of the chart in pixels.
        
        Returns:
            plotly.graph_objects.Figure: The created pie chart.
        """
        names_col = self._resolve_column_ref(names_col)
        if not names_col or names_col not in self.data.columns:
            return self._empty_chart(title)

        source_data = self._clean_category_columns(self.data, [names_col] if names_col else [])
        original_data = self.data
        self.data = source_data
        # Prepare data with aggregation
        agg_result = self._aggregate_data(names_col, values_col, agg_method)
        self.data = original_data
        if isinstance(agg_result, tuple):
            chart_data, result_values_col = agg_result
        else:
            chart_data, result_values_col = agg_result, values_col if values_col else 'count'

        chart_data = chart_data.dropna(subset=[names_col])
        chart_data = self._limit_categories(chart_data, names_col, result_values_col)
        chart_data["_legend_label"] = chart_data[names_col].astype(str).apply(self._shorten_legend_label)
        
        fig = px.pie(
            chart_data, 
            values=result_values_col, 
            names="_legend_label",
            title=title,
            height=height or DEFAULT_PIE_HEIGHT,
            custom_data=[names_col],
        )
        
        fig.update_layout(
            title={
                'text': self._wrap_title(title),
                'y':0.98,
                'x':0.02,
                'xanchor': 'left',
                'yanchor': 'top'
            },
            showlegend=True,
            legend=dict(
                orientation="h",
                y=-0.12,
                yanchor="top",
                x=0,
                xanchor="left",
                traceorder="normal",
                font=dict(size=11),
            ),
            margin=dict(l=42, r=42, t=150, b=126),
        )
        
        # Show only percentages, not labels
        fig.update_traces(
            textposition='inside', 
            textinfo='percent',
            hovertemplate="%{customdata[0]}<br>%{percent}<br>Count: %{value}<extra></extra>"
        )
        
        return self._apply_theme(fig)
    
    def create_line_chart(self, x_col, y_col=None, group_col=None, agg_method="mean", 
                         title="Line Chart", x_label=None, y_label=None, legend_title=None, height=None):
        """
        Create a line chart using Plotly.
        
        Args:
            x_col (str): Column name for x-axis.
            y_col (str, optional): Column name for y-axis. If None, counts are used.
            group_col (str, optional): Column name for line grouping.
            agg_method (str): Aggregation method ('count', 'sum', 'mean', 'median', 'min', 'max', 'count_unique')
            title (str, optional): Chart title.
            x_label (str, optional): X-axis label. Defaults to x_col if None.
            y_label (str, optional): Y-axis label. Defaults to y_col or agg_method if None.
            legend_title (str, optional): Custom title for the legend. Defaults to group_col name.
            height (int, optional): Height of the chart in pixels.
        
        Returns:
            plotly.graph_objects.Figure: The created line chart.
        """
        # Prepare data with aggregation
        agg_result = self._aggregate_data(x_col, y_col, agg_method, group_col)
        if isinstance(agg_result, tuple):
            chart_data, result_y_col = agg_result
        else:
            chart_data, result_y_col = agg_result, y_col if y_col else 'count'
            
        # Set default labels
        if not x_label:
            x_label = x_col
        if not y_label:
            if y_col:
                y_label = f"{agg_method.capitalize()} of {y_col}"
            else:
                y_label = "Count"
        
        # Create the line chart
        fig = px.line(
            chart_data, 
            x=x_col, 
            y=result_y_col, 
            color=group_col,
            title=title,
            labels={
                x_col: x_label,
                result_y_col: y_label
            },
            markers=True,
            height=height or DEFAULT_CHART_HEIGHT
        )
        
        fig.update_layout(
            title={
                'text': self._wrap_title(title),
                'y':0.98,
                'x':0.02,
                'xanchor': 'left',
                'yanchor': 'top'
            },
            legend_title_text=legend_title if legend_title is not None else group_col
        )
        
        return self._apply_theme(fig)
    
    def create_multiple_choice_chart(self, base_column, num_options, option_names=None, 
                               title=None, x_label="Options", y_label="Number of Selections", 
                               color_breakdown=None, legend_title=None, orientation="v", height=None):
        """
        Create a bar chart for multiple-choice questions where respondents can select multiple options.
        
        Args:
            base_column (str): Base name of the columns (e.g., 'a13' for a13_1, a13_2, a13_3)
            num_options (int): Number of options/columns
            option_names (list, optional): Human-readable names for each option
            title (str, optional): Chart title
            x_label (str, optional): X-axis label
            y_label (str, optional): Y-axis label
            color_breakdown (str, optional): Column to use for color breakdown/grouping (e.g., 'sex', 'age_group')
            legend_title (str, optional): Custom title for the legend. Defaults to color_breakdown column name.
            orientation (str, optional): 'v' for vertical bars, 'h' for horizontal
            height (int, optional): Chart height in pixels
            
        Returns:
            plotly.graph_objects.Figure: The created bar chart
        """
        # Generate column names
        columns = [f"{base_column}_{i+1}" for i in range(num_options)]
        
        # Ensure columns exist in the dataframe
        valid_columns = [col for col in columns if col in self.data.columns]
        
        # Default option names if not provided
        if option_names is None:
            option_names = [f"Option {i+1}" for i in range(len(valid_columns))]
        elif len(option_names) < len(valid_columns):
            # Extend option_names if shorter than valid_columns
            option_names.extend([f"Option {i+1}" for i in range(len(option_names), len(valid_columns))])
        
        if color_breakdown is None:
            # Simple approach - no color breakdown
            # Create a dictionary to store counts
            counts = {}
            
            # Count occurrences of each option
            for i, col in enumerate(valid_columns):
                # Count only where value is 1 (selected)
                count = self.data[col].astype(int).sum()
                
                # Use provided option name
                option_label = self._shorten_axis_label(option_names[i], max_length=42)
                counts[option_label] = count
            
            # Convert to DataFrame for visualization
            chart_data = pd.DataFrame({"Option": list(counts.keys()), "Count": list(counts.values())})
            
            # Create the bar chart
            if orientation == "v":
                fig = px.bar(
                    chart_data,
                    x="Option",
                    y="Count",
                    title=title or f"Responses for {base_column}",
                    labels={"Option": x_label, "Count": y_label},
                    height=height or DEFAULT_CHART_HEIGHT
                )
                
                # Add value labels
                fig.update_traces(
                    texttemplate='%{y:.0f}',
                    textposition='outside',
                    textfont=dict(size=10)
                )
            else:
                # Sort data for horizontal bars (largest on top)
                chart_data = chart_data.sort_values("Count")
                
                fig = px.bar(
                    chart_data,
                    x="Count",
                    y="Option",
                    title=title or f"Responses for {base_column}",
                    labels={"Option": x_label, "Count": y_label},
                    orientation='h',
                    height=height or DEFAULT_CHART_HEIGHT
                )
                
                # Add value labels
                fig.update_traces(
                    texttemplate='%{x:.0f}',
                    textposition='outside',
                    textfont=dict(size=10)
                )
        else:
            # Advanced approach - with color breakdown
            # Make sure the color breakdown column exists
            if color_breakdown not in self.data.columns:
                raise ValueError(f"Color breakdown column '{color_breakdown}' not found in data")
                
            # Initialize a list to store data
            chart_data_list = []
            
            # For each option
            for i, col in enumerate(valid_columns):
                option_label = self._shorten_axis_label(option_names[i], max_length=42)
                
                # Get the count grouped by the color breakdown column
                # Only count rows where the option is selected (value = 1)
                # Create a temp dataframe with just the columns we need
                temp_df = self.data[[col, color_breakdown]].copy()
                temp_df = temp_df[temp_df[col] == 1]
                
                # Count by color breakdown column
                breakdown_counts = temp_df[color_breakdown].value_counts().reset_index()
                breakdown_counts.columns = [color_breakdown, 'Count']
                
                # Add option name to each row
                breakdown_counts['Option'] = option_label
                
                # Add to the list
                chart_data_list.append(breakdown_counts)
            
            # Combine all data
            if chart_data_list:
                chart_data = pd.concat(chart_data_list, ignore_index=True)
            else:
                # If no data, create an empty dataframe with the right columns
                chart_data = pd.DataFrame(columns=[color_breakdown, 'Count', 'Option'])
            
            # Create the stacked bar chart
            if orientation == "v":
                fig = px.bar(
                    chart_data,
                    x="Option",
                    y="Count",
                    color=color_breakdown,
                    title=title or f"Responses for {base_column} by {color_breakdown}",
                    labels={"Option": x_label, "Count": y_label},
                    height=height or DEFAULT_CHART_HEIGHT,
                    barmode='stack'
                )
                
                # Add total count annotations
                totals = chart_data.groupby('Option')['Count'].sum().reset_index()
                annotations = []
                for i, row in totals.iterrows():
                    annotations.append(dict(
                        x=row['Option'],
                        y=row['Count'],
                        text=f"{row['Count']:.0f}",
                        showarrow=False,
                        yshift=10,
                        font=dict(size=10)
                    ))
                fig.update_layout(annotations=annotations)
            else:
                # For horizontal bars, sort by total count
                totals = chart_data.groupby('Option')['Count'].sum().reset_index()
                totals = totals.sort_values('Count')
                option_order = totals['Option'].tolist()
                
                # Map the option order to a category with ordered values
                chart_data['Option'] = pd.Categorical(
                    chart_data['Option'], 
                    categories=option_order, 
                    ordered=True
                )
                
                # Sort the data by the ordered category
                chart_data = chart_data.sort_values('Option')
                
                fig = px.bar(
                    chart_data,
                    x="Count",
                    y="Option",
                    color=color_breakdown,
                    title=title or f"Responses for {base_column} by {color_breakdown}",
                    labels={"Option": x_label, "Count": y_label},
                    orientation='h',
                    height=height or DEFAULT_CHART_HEIGHT,
                    barmode='stack'
                )
                
                # Add total count annotations
                annotations = []
                for i, row in totals.iterrows():
                    annotations.append(dict(
                        y=row['Option'],
                        x=row['Count'],
                        text=f"{row['Count']:.0f}",
                        showarrow=False,
                        xshift=10,
                        font=dict(size=10)
                    ))
                fig.update_layout(annotations=annotations)
        
        fig.update_layout(
            title={
                'text': self._wrap_title(title or f"Responses for {base_column}"),
                'y': 0.98,
                'x': 0.02,
                'xanchor': 'left',
                'yanchor': 'top'
            },
            legend_title_text=legend_title if legend_title is not None else color_breakdown
        )
        
        return self._apply_theme(fig)

    def create_selection_summary_chart(self, columns, option_names=None, title="Selection Summary",
                                       x_label="Number", y_label="Component", height=None):
        valid_columns = []
        labels = []
        for idx, column in enumerate(columns):
            col = self._resolve_column_ref(column)
            if col and col in self.data.columns:
                valid_columns.append(col)
                if option_names and idx < len(option_names):
                    labels.append(option_names[idx])
                else:
                    labels.append(str(col).split("/")[-1])

        rows = []
        for col, label in zip(valid_columns, labels):
            rows.append({
                "Option": self._clean_category_label(label),
                "Count": self._truthy_selection_count(self.data[col])
            })
        chart_data = pd.DataFrame(rows)
        if chart_data.empty or "Count" not in chart_data.columns:
            fig = go.Figure()
            fig.add_annotation(text="No selected options available", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
            fig.update_layout(
                title={"text": self._wrap_title(title), "x": 0.02, "xanchor": "left"},
                meta={"empty_chart": True, "empty_reason": "No selected options available"},
            )
            return self._apply_theme(fig)
        chart_data = chart_data[chart_data["Count"] > 0].sort_values("Count", ascending=True)

        if chart_data.empty:
            fig = go.Figure()
            fig.add_annotation(text="No selected options available", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
            fig.update_layout(
                title={"text": self._wrap_title(title), "x": 0.02, "xanchor": "left"},
                meta={"empty_chart": True, "empty_reason": "No selected options available"},
            )
            return self._apply_theme(fig)

        fig = px.bar(
            chart_data,
            x="Count",
            y="Option",
            orientation="h",
            title=title,
            labels={"Count": x_label, "Option": y_label},
            height=height or max(DEFAULT_CHART_HEIGHT, 34 * max(len(chart_data), 8)),
        )
        fig.update_traces(texttemplate="%{x:.0f}", textposition="outside", textfont=dict(size=10))
        fig.update_layout(
            title={"text": self._wrap_title(title), "y": 0.98, "x": 0.02, "xanchor": "left", "yanchor": "top"}
        )
        return self._apply_theme(fig)

    def create_component_text_summary_chart(self, column, component_keywords, title="Component Summary",
                                            x_label="Number", y_label="Component", height=None):
        column = self._resolve_column_ref(column)
        if column not in self.data.columns:
            return self.create_selection_summary_chart([], title=title)

        rows = []
        series = self.data[column].dropna().astype(str)
        for label, keywords in component_keywords.items():
            count = 0
            for value in series:
                lowered = value.lower()
                if any(keyword.lower() in lowered for keyword in keywords):
                    count += 1
            rows.append({"Component": label, "Count": count})

        chart_data = pd.DataFrame(rows)
        chart_data = chart_data[chart_data["Count"] > 0].sort_values("Count", ascending=True)
        if chart_data.empty:
            fig = go.Figure()
            fig.add_annotation(text="No component data available", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
            fig.update_layout(title={"text": self._wrap_title(title), "x": 0.02, "xanchor": "left"})
            return self._apply_theme(fig)

        fig = px.bar(
            chart_data,
            x="Count",
            y="Component",
            orientation="h",
            title=title,
            labels={"Count": x_label, "Component": y_label},
            height=height or max(DEFAULT_CHART_HEIGHT, 34 * max(len(chart_data), 8)),
        )
        fig.update_traces(texttemplate="%{x:.0f}", textposition="outside", textfont=dict(size=10))
        fig.update_layout(
            title={"text": self._wrap_title(title), "y": 0.98, "x": 0.02, "xanchor": "left", "yanchor": "top"}
        )
        return self._apply_theme(fig)
    
    def create_histogram(self, column, bins=None, title=None, x_label=None, y_label="Count", 
                    color=None, color_discrete_map=None, show_normal=False, legend_title=None,
                    show_stats=True, height=None):
        """
        Create a histogram for numerical data.
        
        Args:
            column (str): Column name to plot
            bins (int or list, optional): Number of bins or custom bin edges
            title (str, optional): Chart title. Defaults to "Distribution of {column}"
            x_label (str, optional): X-axis label. Defaults to column name
            y_label (str, optional): Y-axis label. Defaults to "Count"
            color (str, optional): Column to color by (creates multiple histograms)
            color_discrete_map (dict, optional): Mapping of categories to colors
            show_normal (bool, optional): Whether to overlay a normal distribution curve
            legend_title (str, optional): Custom title for the legend. Defaults to color_breakdown column name.
            show_stats (bool, optional): Whether to show lines for mean and median
            height (int, optional): Chart height in pixels
            
        Returns:
            plotly.graph_objects.Figure: The created histogram
        """
        column = self._resolve_column_ref(column)
        if not column or column not in self.data.columns:
            return self._empty_chart(title or "Histogram")

        # Create a copy of the data with just the needed columns
        if color:
            plot_data = self.data[[column, color]].copy()
            # Drop rows with missing values in either column
            plot_data = plot_data.dropna(subset=[column, color])
        else:
            plot_data = self.data[[column]].copy()
            # Drop rows with missing values in the column
            plot_data = plot_data.dropna(subset=[column])

        # Histograms are numeric charts. New survey workbooks can contain text
        # answers such as "Tidak ada perubahan" or Rupiah ranges in otherwise
        # numeric columns, so normalize safe cases and drop non-numeric residue.
        plot_data[column] = self._coerce_numeric_series(plot_data[column])
        plot_data = plot_data.dropna(subset=[column])
        
        # Default title and labels
        title = title or f"Distribution of {column}"
        x_label = x_label or column

        if plot_data.empty:
            fig = go.Figure()
            fig.update_layout(
                title={
                    'text': self._wrap_title(title),
                    'y': 0.98,
                    'x': 0.02,
                    'xanchor': 'left',
                    'yanchor': 'top'
                },
                xaxis_title=x_label,
                yaxis_title=y_label,
            )
            fig.add_annotation(
                text="No numeric data available",
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=14)
            )
            return self._apply_theme(fig)
        
        # Create the histogram
        if color:
            # If coloring by a category, create a histogram for each category
            fig = px.histogram(
                plot_data,
                x=column,
                color=color,
                nbins=bins if isinstance(bins, int) else None,
                color_discrete_map=color_discrete_map,
                title=title,
                labels={column: x_label, "count": y_label},
                height=height or DEFAULT_CHART_HEIGHT,
                opacity=0.9, # Slightly more opaque for stacked mode
                barmode="stack" # Stack the histograms instead of overlay
            )
            
            # Update the legend title if provided
            if legend_title is not None:
                fig.update_layout(legend_title_text=legend_title)
        else:
            # If no color, create a simple histogram
            fig = px.histogram(
                plot_data,
                x=column,
                nbins=bins if isinstance(bins, int) else None,
                title=title,
                labels={column: x_label, "count": y_label},
                height=height or DEFAULT_CHART_HEIGHT,
                color_discrete_sequence=px.colors.qualitative.Plotly if not color_discrete_map else [list(color_discrete_map.values())[0]]
            )
        
        # Add a normal distribution curve if requested
        if show_normal and len(plot_data) > 1:  # Need at least 2 points for mean and std
            mean = plot_data[column].mean()
            std = plot_data[column].std()
            
            # Create 100 evenly spaced points from min to max
            x_min = plot_data[column].min()
            x_max = plot_data[column].max()
            x = np.linspace(x_min, x_max, 100)
            
            # Calculate normal distribution pdf
            from scipy.stats import norm
            pdf = norm.pdf(x, mean, std)
            
            # Scale the pdf to match the histogram height
            if len(plot_data) > 0:
                bin_heights = np.histogram(plot_data[column], bins=bins if isinstance(bins, int) else 10)[0]
                max_height = np.max(bin_heights) if len(bin_heights) > 0 else 1
                pdf = pdf * max_height / np.max(pdf) if np.max(pdf) > 0 else pdf
            
            # Add the normal curve as a scatter trace
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=pdf,
                    mode='lines',
                    name='Normal Distribution',
                    line=dict(color='rgba(0, 100, 80, 0.8)', width=2, dash='dash')
                )
            )
        
        # Add statistical markers if requested
        if show_stats:
            mean = plot_data[column].mean()
            
            # Add a vertical line for the mean
            fig.add_vline(
                x=mean,
                line_color="red",
                line_dash="solid",
                annotation_text=f"Mean: {mean:.2f}",
                annotation_position="top right"
            )
        
        # Update layout
        fig.update_layout(
            title={
                'text': self._wrap_title(title),
                'y': 0.98,
                'x': 0.02,
                'xanchor': 'left',
                'yanchor': 'top'
            },
                        bargap=0.1,  # Gap between bars
            xaxis_title=x_label,
            yaxis_title=y_label,
            legend_title_text=legend_title if legend_title is not None else color
        )
        
        return self._apply_theme(fig)
    
    def create_geo_plot(self, lat_col, lon_col, info_col=None, color_col=None, 
                       title="Geographic Plot", zoom_start=10):
        """
        Create a geographic plot using Folium (Leaflet).
        
        Args:
            lat_col (str): Column name for latitude.
            lon_col (str): Column name for longitude.
            info_col (str or list, optional): Column name(s) for popup information.
            color_col (str, optional): Column name for marker color coding.
            title (str, optional): Chart title.
            zoom_start (int, optional): Initial zoom level.
        
        Returns:
            folium.Map: The created map.
        """
        # Filter out rows with missing lat/lon values
        data = self.data.dropna(subset=[lat_col, lon_col]).copy()
        
        # Convert lat/lon to numeric if they aren't already
        data[lat_col] = pd.to_numeric(data[lat_col], errors='coerce')
        data[lon_col] = pd.to_numeric(data[lon_col], errors='coerce')
        
        # Filter out invalid coordinates
        data = data[(data[lat_col] >= -90) & (data[lat_col] <= 90) & 
                     (data[lon_col] >= -180) & (data[lon_col] <= 180)]
        
        if len(data) == 0:
            st.error("No valid geographic coordinates found in the data.")
            return None
        
        # Calculate map center based on average lat/lon
        center_lat = data[lat_col].mean()
        center_lon = data[lon_col].mean()
        
        # Create map with switchable base layers.
        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles=None)
        folium.TileLayer("OpenStreetMap", name="Standard").add_to(m)
        folium.TileLayer("CartoDB positron", name="Light").add_to(m)
        folium.TileLayer("OpenTopoMap", name="Topo").add_to(m)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles (c) Esri",
            name="Satellite",
            overlay=False,
            control=True,
        ).add_to(m)
        
        # Add title
        title_html = f'<h3 align="center" style="font-size:16px"><b>{title}</b></h3>'
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Create color map if color column is provided
        color_mapping = None
        if color_col:
            if data[color_col].dtype == 'object' or data[color_col].dtype.name == 'category':
                # Categorical data
                unique_categories = data[color_col].unique()
                colors = px.colors.qualitative.Plotly[:len(unique_categories)]
                color_mapping = dict(zip(unique_categories, colors))
            else:
                # Numerical data
                color_scale = px.colors.sequential.Viridis
                vmin, vmax = data[color_col].min(), data[color_col].max()
        
        marker_layer = folium.FeatureGroup(name="Respondent points", overlay=True, control=True, show=True)

        # Add markers
        for idx, row in data.iterrows():
            popup_text = ''
            if info_col:
                if isinstance(info_col, list):
                    popup_text = '<br>'.join([f"{col}: {row[col]}" for col in info_col if col in row])
                else:
                    popup_text = f"{info_col}: {row[info_col]}"
            
            # Determine marker color
            marker_color = 'blue'
            if color_col and color_col in row:
                if color_mapping:
                    # Categorical color
                    marker_color = color_mapping.get(row[color_col], 'blue')
                else:
                    # Numerical color
                    normalized_value = (row[color_col] - vmin) / (vmax - vmin) if vmax != vmin else 0.5
                    color_idx = int(normalized_value * (len(color_scale) - 1))
                    marker_color = color_scale[color_idx]
            
            # Add marker
            folium.CircleMarker(
                location=[row[lat_col], row[lon_col]],
                radius=8,
                popup=folium.Popup(popup_text, max_width=300),
                fill=True,
                fill_opacity=0.7,
                color=marker_color,
                fill_color=marker_color
            ).add_to(marker_layer)

        marker_layer.add_to(m)
        
        # Add color legend if color column is provided
        if color_col and color_mapping:
            legend_html = '''
            <div style="position: fixed; 
                bottom: 50px; right: 50px; width: 150px; height: auto; 
                border:2px solid grey; z-index:9999; font-size:14px;
                background-color:white; padding: 10px;
                ">
            <p style="margin: 0; font-weight: bold;">Legend:</p>
            '''
            for category, color in color_mapping.items():
                legend_html += f'''
                <p style="margin: 0;">
                <span style="display:inline-block; width:12px; height:12px; margin-right:5px; 
                background-color:{color};"></span>{category}</p>
                '''
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))

        folium.LayerControl(collapsed=False).add_to(m)
        
        return m
    
    def create_comparison_bar_chart(self, x_ticks, y1, name1=None, y2=None, name2=None, title='Comparison Bar Chart',
                                    agg_method='sum', x_label=None, y_label=None, orientation='v', height=None):
        """
        Create a comparison bar chart using Plotly. If no second data is given, then create
        a regular bar chart.

        Args:
            x_ticks (list): Tick labels for x-axis.
            y1 (list): Column indices for first data y-axis value.
            y2 (list, optional): Column indices for second data y-axis value.
            name1 (str, optional): Name for first data.
            name2 (str, optional): Name for second data.
            title (str, optional): Chart title.
            agg_method (str): Aggregation method ('count', 'sum'). Defaults to sum.
            x_label (str, optional): X-axis label. Defaults to X if None.
            y_label (str, optional): Y-axis label. Defaults to Count if None.
            orientation (str, optional): Bar orientation ('v' for vertical, 'h' for horizontal).
            height (int, optional): Height of the chart in pixels.

        Returns:
            plotly.graph_objects.Figure: The created comparison bar chart.
        """

        # Set default labels
        if not x_label:
            x_label = 'X'
        if not y_label:
            y_label = 'Count'
        if not name1:
            name1 = 'A'
        x_ticks = [self._shorten_axis_label(tick, max_length=36) for tick in list(x_ticks)]
        if orientation == 'h':
            x_ticks.reverse()
            y1.reverse()

            if y2:
                y2.reverse()
            

        missing_y_refs = 0
        total_y_refs = 0
        y_data_1 = []
        for i in range(len(y1)):
            y_col_1 = self._resolve_column_ref(y1[i])
            total_y_refs += 1

            if not y_col_1 or y_col_1 not in self.data.columns:
                missing_y_refs += 1
                y_1 = 0
            elif agg_method == 'sum':
                y_1 = int(self._coerce_numeric_series(self.data[y_col_1]).sum())
            elif agg_method == 'count':
                y_1 = int(self.data[y_col_1].count())

            y_data_1.append(y_1)

        fig_layout = go.Layout(
            title={
                'text': self._wrap_title(title),
                'y':0.98,
                'x':0.02,
                'xanchor': 'left',
                'yanchor': 'top'
                },
                        height=height or DEFAULT_CHART_HEIGHT,
            barmode='group',
            legend_title_text='Legend',
            xaxis={'title':{'text':x_label if orientation=='v' else y_label}},
            yaxis={'title':{'text':y_label if orientation=='v' else x_label}}
        )

        fig = go.Figure(layout=fig_layout)

        fig.add_trace(go.Bar(
            x=x_ticks if orientation=='v' else y_data_1,
            y=y_data_1 if orientation=='v' else x_ticks,
            name=name1,
            orientation=orientation
        ))

        if y2:
            y_data_2 = []
            for i in range(len(y2)):
                y_col_2 = self._resolve_column_ref(y2[i])
                total_y_refs += 1

                if not y_col_2 or y_col_2 not in self.data.columns:
                    missing_y_refs += 1
                    y_2 = 0
                elif agg_method == 'sum':
                    y_2 = int(self._coerce_numeric_series(self.data[y_col_2]).sum())
                elif agg_method == 'count':
                    y_2 = int(self.data[y_col_2].count())

                y_data_2.append(y_2)

            fig.add_trace(go.Bar(
                x=x_ticks if orientation=='v' else y_data_2,
                y=y_data_2 if orientation=='v' else x_ticks,
                name=name2,
                orientation=orientation
            ))

        if total_y_refs and missing_y_refs == total_y_refs:
            return self._empty_chart(title)

        return self._apply_theme(fig)
