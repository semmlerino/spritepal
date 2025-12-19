# Smart Offset Control Implementation Plan

## Overview
This document details the implementation of a smart offset control feature for SpritePal that filters the ROM navigation to only show sprite-containing regions after scanning, removing empty areas for more efficient navigation.

## 1. Architecture Overview

### Core Concept
- Transform linear ROM offset slider into region-based navigation
- Automatically group nearby sprites into navigable regions
- Provide dual-mode interface: Linear (classic) and Smart (region-based)
- Seamless integration with existing scan workflow

### Key Components
1. **SpriteRegion** - Data structure for sprite groupings with confidence scoring
2. **SpriteRegionDetector** - Algorithm to detect and create regions
3. **SpriteRegionClassifier** - ML-based region type classification
4. **Smart Mode UI** - Enhanced ManualOffsetWidget with dual modes
5. **Region Visualization** - Enhanced ROMMapWidget with region markers
6. **RegionOverviewWidget** - Minimap for quick region navigation
7. **RegionStatisticsPanel** - Detailed region analytics
8. **Persistence Layer** - ROM cache extensions with region-specific invalidation

## 2. New Classes and Data Structures

### utils/sprite_regions.py
```python
from dataclasses import dataclass
from typing import List, Optional, Tuple
import statistics

@dataclass
class SpriteRegion:
    """Represents a contiguous region containing sprites"""
    region_id: int
    start_offset: int
    end_offset: int
    sprite_offsets: List[int]
    sprite_qualities: List[float]
    average_quality: float
    sprite_count: int
    size_bytes: int
    density: float  # sprites per KB
    
    # Enhanced metadata
    confidence_score: float = 1.0  # How confident we are this is a real region
    region_type: str = "unknown"  # e.g., "characters", "backgrounds", "effects"
    is_compressed: bool = True  # Whether sprites in this region are compressed
    access_count: int = 0  # Number of times this region has been accessed
    last_accessed: float = 0.0  # Timestamp of last access
    custom_name: Optional[str] = None  # User-defined region name
    custom_color: Optional[str] = None  # User-defined color for visualization
    
    @property
    def description(self) -> str:
        if self.custom_name:
            return f"{self.custom_name} (Region {self.region_id + 1})"
        return f"Region {self.region_id + 1}: 0x{self.start_offset:06X}-0x{self.end_offset:06X} ({self.sprite_count} sprites)"
    
    @property
    def center_offset(self) -> int:
        """Get the center offset of the region for initial positioning"""
        return (self.start_offset + self.end_offset) // 2
    
    @property
    def quality_category(self) -> str:
        """Categorize region by average quality"""
        if self.average_quality > 0.8:
            return "high"
        elif self.average_quality > 0.5:
            return "medium"
        return "low"

class SpriteRegionDetector:
    """Detects and manages sprite regions from scan results"""
    
    def __init__(self, 
                 gap_threshold: int = 0x10000,  # 64KB default gap
                 min_sprites_per_region: int = 2,
                 min_region_size: int = 0x1000,  # 4KB minimum
                 merge_small_regions: bool = True):
        self.gap_threshold = gap_threshold
        self.min_sprites_per_region = min_sprites_per_region
        self.min_region_size = min_region_size
        self.merge_small_regions = merge_small_regions
        self.regions: List[SpriteRegion] = []
    
    def detect_regions(self, sprites: List[Tuple[int, float]]) -> List[SpriteRegion]:
        """Process sprite list into regions"""
        if not sprites:
            return []
        
        # Sort sprites by offset
        sorted_sprites = sorted(sprites, key=lambda x: x[0])
        
        # Group sprites into regions
        regions = []
        current_region_sprites = [(sorted_sprites[0][0], sorted_sprites[0][1])]
        region_start = sorted_sprites[0][0]
        
        for i in range(1, len(sorted_sprites)):
            offset, quality = sorted_sprites[i]
            prev_offset = sorted_sprites[i-1][0]
            
            # Check if this sprite belongs to current region
            if offset - prev_offset <= self.gap_threshold:
                current_region_sprites.append((offset, quality))
            else:
                # Finalize current region
                region = self._create_region(region_start, current_region_sprites, len(regions))
                if region and self._is_valid_region(region):
                    regions.append(region)
                
                # Start new region
                current_region_sprites = [(offset, quality)]
                region_start = offset
        
        # Don't forget the last region
        region = self._create_region(region_start, current_region_sprites, len(regions))
        if region and self._is_valid_region(region):
            regions.append(region)
        
        # Optionally merge small adjacent regions
        if self.merge_small_regions:
            regions = self._merge_small_regions(regions)
        
        # Re-index regions after potential merging
        for i, region in enumerate(regions):
            region.region_id = i
        
        self.regions = regions
        return regions
    
    def _create_region(self, start: int, sprites: List[Tuple[int, float]], region_id: int) -> Optional[SpriteRegion]:
        """Create a SpriteRegion from sprite list"""
        if not sprites:
            return None
        
        offsets = [s[0] for s in sprites]
        qualities = [s[1] for s in sprites]
        
        end_offset = max(offsets) + 0x1000  # Add some padding
        size_bytes = end_offset - start
        density = len(sprites) / (size_bytes / 1024) if size_bytes > 0 else 0
        
        return SpriteRegion(
            region_id=region_id,
            start_offset=start,
            end_offset=end_offset,
            sprite_offsets=offsets,
            sprite_qualities=qualities,
            average_quality=statistics.mean(qualities) if qualities else 0,
            sprite_count=len(sprites),
            size_bytes=size_bytes,
            density=density
        )
    
    def _is_valid_region(self, region: SpriteRegion) -> bool:
        """Check if region meets minimum requirements"""
        return (region.sprite_count >= self.min_sprites_per_region and
                region.size_bytes >= self.min_region_size)
    
    def _merge_small_regions(self, regions: List[SpriteRegion]) -> List[SpriteRegion]:
        """Merge small adjacent regions"""
        if len(regions) <= 1:
            return regions
        
        merged = []
        i = 0
        while i < len(regions):
            current = regions[i]
            
            # Check if should merge with next region
            if (i + 1 < len(regions) and 
                current.size_bytes < self.min_region_size * 2 and
                regions[i + 1].start_offset - current.end_offset < self.gap_threshold):
                # Merge with next region
                next_region = regions[i + 1]
                merged_sprites = list(zip(
                    current.sprite_offsets + next_region.sprite_offsets,
                    current.sprite_qualities + next_region.sprite_qualities
                ))
                merged_region = self._create_region(
                    current.start_offset,
                    merged_sprites,
                    len(merged)
                )
                if merged_region:
                    merged.append(merged_region)
                i += 2  # Skip next region
            else:
                merged.append(current)
                i += 1
        
        return merged
    
    def find_region_for_offset(self, offset: int) -> Optional[int]:
        """Find which region contains the given offset"""
        for i, region in enumerate(self.regions):
            if region.start_offset <= offset <= region.end_offset:
                return i
        return None
    
    def get_nearest_sprite(self, offset: int, direction: int = 1) -> Optional[int]:
        """Find nearest sprite in given direction (1=forward, -1=backward)"""
        all_sprites = []
        for region in self.regions:
            all_sprites.extend(region.sprite_offsets)
        
        if not all_sprites:
            return None
        
        all_sprites.sort()
        
        if direction > 0:
            # Find next sprite
            for sprite_offset in all_sprites:
                if sprite_offset > offset:
                    return sprite_offset
        else:
            # Find previous sprite
            for sprite_offset in reversed(all_sprites):
                if sprite_offset < offset:
                    return sprite_offset
        
        return None

class SpriteRegionClassifier:
    """Classifies sprite regions by type based on patterns"""
    
    def __init__(self):
        self.classification_rules = {
            "characters": {
                "min_sprite_count": 4,
                "max_sprite_count": 50,
                "typical_density": (0.5, 2.0),  # sprites per KB
                "typical_sizes": (0x2000, 0x10000)  # 8KB to 64KB
            },
            "backgrounds": {
                "min_sprite_count": 10,
                "max_sprite_count": 200,
                "typical_density": (1.0, 5.0),
                "typical_sizes": (0x4000, 0x20000)  # 16KB to 128KB
            },
            "effects": {
                "min_sprite_count": 1,
                "max_sprite_count": 20,
                "typical_density": (0.1, 1.0),
                "typical_sizes": (0x1000, 0x8000)  # 4KB to 32KB
            }
        }
    
    def classify_region(self, region: SpriteRegion) -> Tuple[str, float]:
        """Classify a region and return type with confidence score"""
        best_match = "unknown"
        best_confidence = 0.0
        
        for region_type, rules in self.classification_rules.items():
            confidence = 0.0
            factors = 0
            
            # Check sprite count
            if rules["min_sprite_count"] <= region.sprite_count <= rules["max_sprite_count"]:
                confidence += 0.3
            factors += 0.3
            
            # Check density
            min_density, max_density = rules["typical_density"]
            if min_density <= region.density <= max_density:
                confidence += 0.3
            factors += 0.3
            
            # Check size
            min_size, max_size = rules["typical_sizes"]
            if min_size <= region.size_bytes <= max_size:
                confidence += 0.2
            factors += 0.2
            
            # Check quality distribution
            if region.average_quality > 0.7:
                confidence += 0.2
            factors += 0.2
            
            # Normalize confidence
            normalized_confidence = confidence / factors if factors > 0 else 0
            
            if normalized_confidence > best_confidence:
                best_confidence = normalized_confidence
                best_match = region_type
        
        return best_match, best_confidence

# Thread pool for parallel region calculation
from concurrent.futures import ThreadPoolExecutor
import threading

class ParallelRegionDetector(SpriteRegionDetector):
    """Multi-threaded version of region detector for large sprite sets"""
    
    def __init__(self, *args, num_threads: int = 4, **kwargs):
        super().__init__(*args, **kwargs)
        self.num_threads = num_threads
        self._lock = threading.Lock()
    
    def detect_regions(self, sprites: List[Tuple[int, float]]) -> List[SpriteRegion]:
        """Process sprite list into regions using multiple threads"""
        if not sprites or len(sprites) < 100:
            # Use single-threaded for small datasets
            return super().detect_regions(sprites)
        
        # Sort sprites by offset
        sorted_sprites = sorted(sprites, key=lambda x: x[0])
        
        # Divide work into chunks
        chunk_size = max(50, len(sorted_sprites) // self.num_threads)
        chunks = []
        
        for i in range(0, len(sorted_sprites), chunk_size):
            chunk = sorted_sprites[i:i + chunk_size]
            if chunk:
                chunks.append(chunk)
        
        # Process chunks in parallel
        regions = []
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = []
            for chunk in chunks:
                future = executor.submit(self._process_chunk, chunk)
                futures.append(future)
            
            # Collect results
            for future in futures:
                chunk_regions = future.result()
                regions.extend(chunk_regions)
        
        # Merge adjacent regions from different chunks
        regions = self._merge_chunk_boundaries(regions)
        
        # Re-index regions
        for i, region in enumerate(regions):
            region.region_id = i
        
        self.regions = regions
        return regions
    
    def _process_chunk(self, sprites: List[Tuple[int, float]]) -> List[SpriteRegion]:
        """Process a chunk of sprites into regions"""
        # Reuse parent's region detection logic
        temp_detector = SpriteRegionDetector(
            self.gap_threshold,
            self.min_sprites_per_region,
            self.min_region_size,
            False  # Don't merge within chunks
        )
        return temp_detector.detect_regions(sprites)
```

## 3. UI Modifications

### ManualOffsetWidget Enhancements
```python
class ManualOffsetWidget(BaseExtractionWidget):
    # New signals
    smart_mode_changed = Signal(bool)
    region_changed = Signal(int)  # region index
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # ... existing init code ...
        
        # Smart mode attributes
        self._smart_mode_enabled = False
        self._sprite_regions: List[SpriteRegion] = []
        self._current_region_index = 0
        self._region_detector = SpriteRegionDetector()
        self._region_boundaries: List[int] = []  # Slider positions for region boundaries
        self._region_weights: List[float] = []  # Relative sizes of regions
        
    def _setup_ui(self):
        # ... existing UI setup ...
        
        # Add smart mode controls after offset row
        smart_mode_row = QHBoxLayout()
        smart_mode_row.setSpacing(SPACING_MEDIUM)
        
        self.smart_mode_checkbox = QCheckBox("Smart Navigation")
        self.smart_mode_checkbox.setToolTip(
            "Navigate only through sprite-containing regions\n"
            "Removes empty areas from the slider range"
        )
        self.smart_mode_checkbox.stateChanged.connect(self._on_smart_mode_toggled)
        smart_mode_row.addWidget(self.smart_mode_checkbox)
        
        # Region indicator
        self.region_indicator_label = QLabel("Linear Mode")
        self.region_indicator_label.setStyleSheet("""
            color: #66aaff;
            font-weight: bold;
            padding: 2px 6px;
            background: #1a1a1a;
            border: 1px solid #444444;
            border-radius: 3px;
        """)
        smart_mode_row.addWidget(self.region_indicator_label)
        
        smart_mode_row.addStretch()
        manual_layout.insertLayout(3, smart_mode_row)  # Insert after offset controls
        
        # Region navigation controls (initially hidden)
        self.region_nav_widget = QWidget()
        region_nav_layout = QHBoxLayout()
        region_nav_layout.setContentsMargins(0, 0, 0, 0)
        region_nav_layout.setSpacing(SPACING_MEDIUM)
        
        self.prev_region_btn = QPushButton("← Prev Region")
        self.prev_region_btn.setToolTip("Jump to previous sprite region (Ctrl+Left)")
        self.prev_region_btn.clicked.connect(self._navigate_prev_region)
        region_nav_layout.addWidget(self.prev_region_btn)
        
        self.region_info_label = QLabel("")
        self.region_info_label.setStyleSheet("color: #888888;")
        region_nav_layout.addWidget(self.region_info_label)
        
        self.next_region_btn = QPushButton("Next Region →")
        self.next_region_btn.setToolTip("Jump to next sprite region (Ctrl+Right)")
        self.next_region_btn.clicked.connect(self._navigate_next_region)
        region_nav_layout.addWidget(self.next_region_btn)
        
        region_nav_layout.addStretch()
        self.region_nav_widget.setLayout(region_nav_layout)
        self.region_nav_widget.setVisible(False)
        
        manual_layout.insertWidget(5, self.region_nav_widget)  # After navigation buttons
        
        # Add region overview button
        self.region_overview_btn = QPushButton("📊 Region Overview")
        self.region_overview_btn.setToolTip("Show minimap of all regions (M)")
        self.region_overview_btn.clicked.connect(self._show_region_overview)
        manual_layout.addWidget(self.region_overview_btn)
        
        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
        # Setup slider visual enhancements
        self._setup_slider_visuals()
    
    def _setup_keyboard_shortcuts(self):
        """Setup comprehensive keyboard shortcuts"""
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QShortcut
        
        # Region navigation
        QShortcut(QKeySequence("Ctrl+Left"), self, self._navigate_prev_region)
        QShortcut(QKeySequence("Ctrl+Right"), self, self._navigate_next_region)
        QShortcut(QKeySequence("Home"), self, self._navigate_first_region)
        QShortcut(QKeySequence("End"), self, self._navigate_last_region)
        
        # Quick region jumping (1-9 keys)
        for i in range(1, 10):
            QShortcut(QKeySequence(str(i)), self, lambda idx=i-1: self._jump_to_region(idx))
        
        # Mode toggling
        QShortcut(QKeySequence("R"), self, self._toggle_smart_mode)
        QShortcut(QKeySequence("M"), self, self._show_region_overview)
        
        # Navigation history
        QShortcut(QKeySequence("Alt+Left"), self, self._navigate_back)
        QShortcut(QKeySequence("Alt+Right"), self, self._navigate_forward)
    
    def _setup_slider_visuals(self):
        """Add visual region markers to slider"""
        # Create custom slider widget with region markers
        self.offset_slider.installEventFilter(self)
        self._slider_painter = RegionSliderPainter(self.offset_slider)
```

### Enhanced Slider Widget
```python
class RegionSliderPainter:
    """Paints region boundaries on the slider track"""
    
    def __init__(self, slider: QSlider):
        self.slider = slider
        self.region_boundaries: List[int] = []
        self.region_colors: List[QColor] = []
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        self.animation_progress = 0.0
        self.transitioning = False
    
    def set_regions(self, boundaries: List[int], regions: List[SpriteRegion]):
        """Update region boundaries and colors"""
        self.region_boundaries = boundaries
        self.region_colors = []
        
        for region in regions:
            if region.custom_color:
                color = QColor(region.custom_color)
            else:
                # Auto-color based on quality
                if region.quality_category == "high":
                    color = QColor(100, 255, 100, 60)
                elif region.quality_category == "medium":
                    color = QColor(255, 255, 100, 60)
                else:
                    color = QColor(255, 100, 100, 60)
            self.region_colors.append(color)
    
    def start_transition(self):
        """Start smooth transition animation"""
        self.transitioning = True
        self.animation_progress = 0.0
        self.animation_timer.start(16)  # 60 FPS
    
    def paint_regions(self, painter: QPainter, rect: QRect):
        """Paint region markers on slider track"""
        if not self.region_boundaries:
            return
        
        # Draw region boundaries
        for i in range(len(self.region_boundaries) - 1):
            start_x = self._map_to_pixel(self.region_boundaries[i], rect)
            end_x = self._map_to_pixel(self.region_boundaries[i + 1], rect)
            
            # Draw region background
            if i < len(self.region_colors):
                painter.fillRect(start_x, rect.y(), end_x - start_x, rect.height(), 
                               self.region_colors[i])
            
            # Draw boundary line
            painter.setPen(QPen(Qt.GlobalColor.gray, 1, Qt.PenStyle.DashLine))
            painter.drawLine(start_x, rect.y(), start_x, rect.y() + rect.height())
```

### Slider Mapping Methods
```python
def _setup_region_mapping(self):
    """Calculate slider mapping for regions"""
    if not self._sprite_regions:
        return
    
    # Calculate weights based on region size
    total_size = sum(r.size_bytes for r in self._sprite_regions)
    self._region_weights = [r.size_bytes / total_size for r in self._sprite_regions]
    
    # Calculate slider boundaries for each region
    self._region_boundaries = [0]
    cumulative = 0
    slider_max = self.offset_slider.maximum()
    
    for weight in self._region_weights:
        cumulative += weight * slider_max
        self._region_boundaries.append(int(cumulative))

def _map_slider_to_offset(self, slider_value: int) -> int:
    """Map slider position to ROM offset based on mode"""
    if not self._smart_mode_enabled or not self._sprite_regions:
        return slider_value  # Linear mapping
    
    # Find which region this slider value falls into
    for i in range(len(self._region_boundaries) - 1):
        if self._region_boundaries[i] <= slider_value < self._region_boundaries[i + 1]:
            # Interpolate within the region
            region = self._sprite_regions[i]
            region_start_slider = self._region_boundaries[i]
            region_end_slider = self._region_boundaries[i + 1]
            
            # Calculate position within region (0-1)
            if region_end_slider > region_start_slider:
                position = (slider_value - region_start_slider) / (region_end_slider - region_start_slider)
            else:
                position = 0
            
            # Map to actual offset
            offset = int(region.start_offset + position * (region.end_offset - region.start_offset))
            return offset
    
    # Fallback for edge cases
    return self._sprite_regions[-1].end_offset if self._sprite_regions else slider_value

def _map_offset_to_slider(self, offset: int) -> int:
    """Map ROM offset to slider position based on mode"""
    if not self._smart_mode_enabled or not self._sprite_regions:
        return offset  # Linear mapping
    
    # Find which region contains this offset
    region_index = self._region_detector.find_region_for_offset(offset)
    if region_index is None:
        # Offset is outside any region, find nearest
        for i, region in enumerate(self._sprite_regions):
            if offset < region.start_offset:
                region_index = max(0, i - 1)
                break
        else:
            region_index = len(self._sprite_regions) - 1
    
    if 0 <= region_index < len(self._sprite_regions):
        region = self._sprite_regions[region_index]
        region_start_slider = self._region_boundaries[region_index]
        region_end_slider = self._region_boundaries[region_index + 1]
        
        # Calculate position within region
        if region.end_offset > region.start_offset:
            position = (offset - region.start_offset) / (region.end_offset - region.start_offset)
            position = max(0, min(1, position))  # Clamp to 0-1
        else:
            position = 0
        
        # Map to slider position
        slider_pos = int(region_start_slider + position * (region_end_slider - region_start_slider))
        return slider_pos
    
    return 0
```

### RegionOverviewWidget
```python
class RegionOverviewWidget(QDialog):
    """Minimap showing all regions for quick navigation"""
    
    region_selected = Signal(int)  # Emit region index when clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Region Overview")
        self.setModal(False)  # Non-modal for easy access
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(600, 400)
        
        self.regions: List[SpriteRegion] = []
        self.current_region = -1
        self.hovered_region = -1
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        
        # Custom widget for region visualization
        self.region_view = RegionMapView()
        self.region_view.region_clicked.connect(self.region_selected.emit)
        layout.addWidget(self.region_view)
        
        # Region list with details
        self.region_list = QListWidget()
        self.region_list.itemClicked.connect(self._on_list_item_clicked)
        layout.addWidget(self.region_list)
        
        # Bookmarks section
        bookmark_layout = QHBoxLayout()
        bookmark_layout.addWidget(QLabel("Bookmarks:"))
        self.bookmark_combo = QComboBox()
        bookmark_layout.addWidget(self.bookmark_combo)
        self.add_bookmark_btn = QPushButton("+ Add")
        self.add_bookmark_btn.clicked.connect(self._add_bookmark)
        bookmark_layout.addWidget(self.add_bookmark_btn)
        layout.addLayout(bookmark_layout)
        
        self.setLayout(layout)
    
    def set_regions(self, regions: List[SpriteRegion]):
        """Update the displayed regions"""
        self.regions = regions
        self.region_view.set_regions(regions)
        self._update_region_list()
    
    def _update_region_list(self):
        """Update the region detail list"""
        self.region_list.clear()
        for i, region in enumerate(self.regions):
            item_text = f"{region.description}\n"
            item_text += f"   Quality: {region.quality_category} ({region.average_quality:.2f})\n"
            item_text += f"   Type: {region.region_type}\n"
            item_text += f"   Size: {region.size_bytes / 1024:.1f} KB"
            
            item = QListWidgetItem(item_text)
            if region.custom_color:
                item.setBackground(QColor(region.custom_color))
            self.region_list.addItem(item)

class RegionMapView(QWidget):
    """Visual representation of regions as clickable blocks"""
    
    region_clicked = Signal(int)
    
    def __init__(self):
        super().__init__()
        self.regions: List[SpriteRegion] = []
        self.setMinimumHeight(100)
        self.setMouseTracking(True)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not self.regions:
            return
        
        # Calculate layout
        width = self.width()
        height = self.height()
        total_size = sum(r.size_bytes for r in self.regions)
        
        x = 0
        for i, region in enumerate(self.regions):
            # Calculate region width proportional to size
            region_width = int((region.size_bytes / total_size) * width)
            
            # Draw region block
            color = QColor(region.custom_color) if region.custom_color else self._get_auto_color(region)
            painter.fillRect(x, 20, region_width, height - 40, color)
            
            # Draw border
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.drawRect(x, 20, region_width, height - 40)
            
            # Draw label if space permits
            if region_width > 40:
                painter.setPen(Qt.GlobalColor.black)
                painter.drawText(x + 5, 35, f"R{i+1}")
            
            x += region_width
```

### RegionStatisticsPanel
```python
class RegionStatisticsPanel(QWidget):
    """Detailed statistics for the current region"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_region: Optional[SpriteRegion] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        self.title_label = QLabel("Region Statistics")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.title_label)
        
        # Stats grid
        stats_layout = QGridLayout()
        
        # Region info
        stats_layout.addWidget(QLabel("Region:"), 0, 0)
        self.region_name_label = QLabel("--")
        stats_layout.addWidget(self.region_name_label, 0, 1)
        
        stats_layout.addWidget(QLabel("Type:"), 1, 0)
        self.region_type_label = QLabel("--")
        stats_layout.addWidget(self.region_type_label, 1, 1)
        
        stats_layout.addWidget(QLabel("Confidence:"), 2, 0)
        self.confidence_label = QLabel("--")
        stats_layout.addWidget(self.confidence_label, 2, 1)
        
        # Sprite stats
        stats_layout.addWidget(QLabel("Sprites:"), 3, 0)
        self.sprite_count_label = QLabel("--")
        stats_layout.addWidget(self.sprite_count_label, 3, 1)
        
        stats_layout.addWidget(QLabel("Density:"), 4, 0)
        self.density_label = QLabel("--")
        stats_layout.addWidget(self.density_label, 4, 1)
        
        stats_layout.addWidget(QLabel("Quality:"), 5, 0)
        self.quality_label = QLabel("--")
        stats_layout.addWidget(self.quality_label, 5, 1)
        
        # Access stats
        stats_layout.addWidget(QLabel("Accessed:"), 6, 0)
        self.access_count_label = QLabel("--")
        stats_layout.addWidget(self.access_count_label, 6, 1)
        
        stats_layout.addWidget(QLabel("Last Access:"), 7, 0)
        self.last_access_label = QLabel("--")
        stats_layout.addWidget(self.last_access_label, 7, 1)
        
        layout.addLayout(stats_layout)
        
        # Quality distribution chart
        self.quality_chart = QualityDistributionChart()
        layout.addWidget(self.quality_chart)
        
        # Region controls
        control_layout = QHBoxLayout()
        self.rename_btn = QPushButton("Rename")
        self.rename_btn.clicked.connect(self._rename_region)
        control_layout.addWidget(self.rename_btn)
        
        self.recolor_btn = QPushButton("Change Color")
        self.recolor_btn.clicked.connect(self._recolor_region)
        control_layout.addWidget(self.recolor_btn)
        
        self.merge_btn = QPushButton("Merge")
        self.merge_btn.setToolTip("Merge with adjacent region")
        control_layout.addWidget(self.merge_btn)
        
        self.split_btn = QPushButton("Split")
        self.split_btn.setToolTip("Split region at cursor")
        control_layout.addWidget(self.split_btn)
        
        layout.addLayout(control_layout)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def set_region(self, region: SpriteRegion):
        """Update displayed statistics for a region"""
        self.current_region = region
        
        # Update labels
        self.region_name_label.setText(region.description)
        self.region_type_label.setText(region.region_type.title())
        self.confidence_label.setText(f"{region.confidence_score:.0%}")
        self.sprite_count_label.setText(str(region.sprite_count))
        self.density_label.setText(f"{region.density:.2f} sprites/KB")
        self.quality_label.setText(f"{region.quality_category} ({region.average_quality:.2f})")
        self.access_count_label.setText(str(region.access_count))
        
        if region.last_accessed > 0:
            from datetime import datetime
            last_access = datetime.fromtimestamp(region.last_accessed)
            self.last_access_label.setText(last_access.strftime("%H:%M:%S"))
        else:
            self.last_access_label.setText("Never")
        
        # Update quality chart
        self.quality_chart.set_qualities(region.sprite_qualities)
```

## 4. Integration Points

### ScanControlsPanel Changes
```python
class ScanControlsPanel(QWidget):
    # Add new signal
    sprites_detected = Signal(list)  # List of (offset, quality) tuples
    
    def _on_range_scan_complete(self, success: bool):
        """Handle range scan completion"""
        self._finish_scan()
        
        # Update final status
        sprite_count = len(self.found_sprites)
        if sprite_count > 0:
            self.scan_status_changed.emit(f"Range scan complete: {sprite_count} sprites found")
            # Emit sprites for smart mode processing
            self.sprites_detected.emit(self.found_sprites)
        else:
            self.scan_status_changed.emit("Range scan complete: No sprites found")
    
    def _on_sprite_found(self, offset: int, quality: float):
        """Handle sprite found during scan for real-time region updates"""
        # Existing sprite found handling...
        
        # Emit for real-time region formation
        if hasattr(self, 'real_time_update_timer'):
            self.pending_sprites.append((offset, quality))
            if not self.real_time_update_timer.isActive():
                self.real_time_update_timer.start(500)  # Update every 500ms
    
    def _emit_partial_sprites(self):
        """Emit partial sprite list for real-time region visualization"""
        if self.pending_sprites:
            self.sprites_detected.emit(self.found_sprites + self.pending_sprites)
            self.pending_sprites.clear()
```

### Enhanced Find Next/Previous Integration
```python
class ManualOffsetWidget(BaseExtractionWidget):
    def _find_next_sprite(self):
        """Find next sprite with smart mode awareness"""
        if self._smart_mode_enabled and self._sprite_regions:
            # In smart mode, constrain to current region by default
            current_region = self._sprite_regions[self._current_region_index]
            
            # Check if we should expand search
            if self._should_expand_search():
                # Search in next region
                if self._current_region_index < len(self._sprite_regions) - 1:
                    self._navigate_next_region()
                    return
            
            # Search within current region
            next_sprite = self._region_detector.get_nearest_sprite(
                self.current_offset, direction=1
            )
            if next_sprite and current_region.start_offset <= next_sprite <= current_region.end_offset:
                self.set_offset(next_sprite)
            else:
                # Offer to expand search
                self._prompt_expand_search()
        else:
            # Linear mode - existing behavior
            super()._find_next_sprite()
    
    def _should_expand_search(self) -> bool:
        """Check if search should expand beyond current region"""
        # Could be based on user preference or search history
        return self._expand_search_enabled
    
    def _prompt_expand_search(self):
        """Ask user if they want to search in other regions"""
        reply = QMessageBox.question(
            self,
            "Expand Search?",
            "No more sprites found in current region.\n"
            "Search in other regions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._expand_search_enabled = True
            self._find_next_sprite()
```

### Dynamic Region Updates
```python
class RegionUpdateManager:
    """Manages dynamic region updates as new sprites are discovered"""
    
    def __init__(self, detector: SpriteRegionDetector):
        self.detector = detector
        self.known_sprites: Set[int] = set()
        self.update_callback: Optional[Callable] = None
    
    def add_discovered_sprite(self, offset: int, quality: float):
        """Add a newly discovered sprite and update regions if needed"""
        if offset in self.known_sprites:
            return False
        
        self.known_sprites.add(offset)
        
        # Check if this sprite falls within existing regions
        region_index = self.detector.find_region_for_offset(offset)
        
        if region_index is not None:
            # Add to existing region
            region = self.detector.regions[region_index]
            region.sprite_offsets.append(offset)
            region.sprite_qualities.append(quality)
            region.sprite_count += 1
            region.average_quality = statistics.mean(region.sprite_qualities)
            return True
        else:
            # Sprite is outside known regions - may need new region
            self._check_new_region_needed(offset, quality)
            return True
    
    def _check_new_region_needed(self, offset: int, quality: float):
        """Check if a new region should be created"""
        # Find nearest existing region
        nearest_region = None
        min_distance = float('inf')
        
        for region in self.detector.regions:
            distance = min(
                abs(offset - region.start_offset),
                abs(offset - region.end_offset)
            )
            if distance < min_distance:
                min_distance = distance
                nearest_region = region
        
        # If close enough to existing region, expand it
        if nearest_region and min_distance < self.detector.gap_threshold:
            if offset < nearest_region.start_offset:
                nearest_region.start_offset = offset
            elif offset > nearest_region.end_offset:
                nearest_region.end_offset = offset + 0x1000
            
            nearest_region.sprite_offsets.append(offset)
            nearest_region.sprite_qualities.append(quality)
            nearest_region.sprite_count += 1
            nearest_region.size_bytes = nearest_region.end_offset - nearest_region.start_offset
            nearest_region.density = nearest_region.sprite_count / (nearest_region.size_bytes / 1024)
        else:
            # Create new single-sprite region
            new_region = SpriteRegion(
                region_id=len(self.detector.regions),
                start_offset=offset,
                end_offset=offset + 0x1000,
                sprite_offsets=[offset],
                sprite_qualities=[quality],
                average_quality=quality,
                sprite_count=1,
                size_bytes=0x1000,
                density=1.0,
                region_type="discovered"
            )
            self.detector.regions.append(new_region)
            self.detector.regions.sort(key=lambda r: r.start_offset)
            
            # Re-index regions
            for i, region in enumerate(self.detector.regions):
                region.region_id = i
        
        # Trigger UI update
        if self.update_callback:
            self.update_callback()
```

### ManualOffsetDialog Integration
```python
def _connect_signals(self):
    """Connect internal signals"""
    # ... existing connections ...
    
    # Connect scan completion to smart mode
    self.scan_controls.sprites_detected.connect(self._on_sprites_detected)
    
def _on_sprites_detected(self, sprites: List[Tuple[int, float]]):
    """Handle sprites detected from scan"""
    if sprites:
        # Update offset widget with sprite regions
        self.offset_widget.set_sprite_regions(sprites)
        
        # Update ROM map with regions
        if hasattr(self, 'rom_map'):
            regions = self.offset_widget.get_sprite_regions()
            self.rom_map.set_sprite_regions(regions)
```

## 5. ROMMapWidget Enhancements

```python
class ROMMapWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # ... existing init ...
        self.sprite_regions: List[SpriteRegion] = []
        self.current_region_index: int = -1
        self.highlight_regions: bool = True
    
    def set_sprite_regions(self, regions: List[SpriteRegion]):
        """Set sprite regions for visualization"""
        self.sprite_regions = regions
        self.update()
    
    def set_current_region(self, region_index: int):
        """Highlight the current region"""
        if self.current_region_index != region_index:
            self.current_region_index = region_index
            self.update()
    
    @override
    def paintEvent(self, event: QPaintEvent | None):
        """Enhanced paint event with region visualization"""
        # ... existing paint code ...
        
        # Draw regions if in smart mode
        if self.sprite_regions and self.highlight_regions:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            for i, region in enumerate(self.sprite_regions):
                if 0 <= region.start_offset < self.rom_size:
                    x_start = int((region.start_offset / self.rom_size) * width)
                    x_end = int((region.end_offset / self.rom_size) * width)
                    
                    # Different colors for current/other regions
                    if i == self.current_region_index:
                        painter.fillRect(x_start, 10, x_end - x_start, height - 20, 
                                       QColor(100, 150, 255, 60))  # Highlighted blue
                        painter.setPen(QPen(QColor(100, 150, 255), 2))
                    else:
                        painter.fillRect(x_start, 10, x_end - x_start, height - 20, 
                                       QColor(80, 80, 80, 40))  # Subtle gray
                        painter.setPen(QPen(QColor(120, 120, 120), 1))
                    
                    # Draw region boundaries
                    painter.drawRect(x_start, 10, x_end - x_start, height - 20)
                    
                    # Draw region number if space permits
                    if x_end - x_start > 20:
                        painter.setPen(Qt.GlobalColor.white)
                        painter.setFont(QFont("Arial", 8))
                        painter.drawText(x_start + 2, 25, f"R{i+1}")
```

## 6. Caching Integration

### ROM Cache Extensions
```python
# In utils/rom_cache.py
def save_sprite_regions(self, rom_path: str, regions: List[dict[str, Any]]) -> bool:
    """Save sprite regions for a ROM"""
    if not self._cache_enabled:
        return False
    
    try:
        rom_hash = self._get_rom_hash(rom_path)
        cache_file = self._get_cache_file_path(rom_hash, "sprite_regions")
        
        cache_data = {
            "version": self.CACHE_VERSION,
            "rom_path": os.path.abspath(rom_path),
            "rom_hash": rom_hash,
            "cached_at": time.time(),
            "sprite_regions": regions
        }
        
        return self._save_cache_data(cache_file, cache_data)
    
    except Exception as e:
        logger.warning(f"Failed to save sprite regions to cache: {e}")
        return False

def get_sprite_regions(self, rom_path: str) -> List[dict[str, Any]] | None:
    """Get cached sprite regions for a ROM"""
    if not self._cache_enabled:
        return None
    
    try:
        rom_hash = self._get_rom_hash(rom_path)
        cache_file = self._get_cache_file_path(rom_hash, "sprite_regions")
        
        if not self._is_cache_valid(cache_file, rom_path):
            return None
        
        cache_data = self._load_cache_data(cache_file)
        if not cache_data:
            return None
        
        if (cache_data.get("version") != self.CACHE_VERSION or
            "sprite_regions" not in cache_data):
            return None
        
        return cache_data["sprite_regions"]
    
    except Exception as e:
        logger.warning(f"Failed to load sprite regions from cache: {e}")
        return None
```

## 7. Settings Persistence

```python
# In ManualOffsetWidget
def save_smart_mode_settings(self):
    """Save smart mode preferences"""
    settings = get_settings_manager()
    rom_key = self._get_rom_key()  # Hash or path-based key
    
    settings.set_value(f"smart_mode/{rom_key}/enabled", self._smart_mode_enabled)
    settings.set_value(f"smart_mode/{rom_key}/region_index", self._current_region_index)
    settings.set_value(f"smart_mode/gap_threshold", self._region_detector.gap_threshold)
    settings.set_value(f"smart_mode/min_sprites_per_region", self._region_detector.min_sprites_per_region)

def load_smart_mode_settings(self):
    """Load smart mode preferences"""
    settings = get_settings_manager()
    rom_key = self._get_rom_key()
    
    # Load global preferences
    self._region_detector.gap_threshold = settings.get_value(
        "smart_mode/gap_threshold", 0x10000, int
    )
    self._region_detector.min_sprites_per_region = settings.get_value(
        "smart_mode/min_sprites_per_region", 2, int
    )
    
    # Load ROM-specific preferences
    if rom_key:
        enabled = settings.get_value(f"smart_mode/{rom_key}/enabled", False, bool)
        if enabled and self._sprite_regions:
            self.smart_mode_checkbox.setChecked(True)
            
        saved_region = settings.get_value(f"smart_mode/{rom_key}/region_index", 0, int)
        if 0 <= saved_region < len(self._sprite_regions):
            self._current_region_index = saved_region
```

## 8. Error Handling

```python
def _on_smart_mode_toggled(self, checked: bool):
    """Handle smart mode toggle with error recovery"""
    try:
        if checked:
            # Attempt to enable smart mode
            if not self._sprite_regions:
                # No regions available
                QMessageBox.information(
                    self,
                    "Smart Mode",
                    "No sprite regions detected.\n\n"
                    "Please run a ROM scan first to detect sprite locations."
                )
                self.smart_mode_checkbox.setChecked(False)
                return
            
            if len(self._sprite_regions) == 1:
                # Only one region - not much benefit
                reply = QMessageBox.question(
                    self,
                    "Smart Mode",
                    "Only one sprite region detected.\n"
                    "Smart mode may not provide much benefit.\n\n"
                    "Enable anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.smart_mode_checkbox.setChecked(False)
                    return
            
            self._enable_smart_mode()
        else:
            self._disable_smart_mode()
    
    except Exception as e:
        logger.exception("Error toggling smart mode")
        QMessageBox.critical(
            self,
            "Smart Mode Error",
            f"Failed to toggle smart mode:\n{str(e)}\n\n"
            "Reverting to linear mode."
        )
        self._disable_smart_mode()
        self.smart_mode_checkbox.setChecked(False)
```

## 9. Performance Optimizations

```python
class ManualOffsetWidget(BaseExtractionWidget):
    def __init__(self, parent=None):
        # ... existing init ...
        
        # Performance optimization flags
        self._region_calculation_pending = False
        self._slider_update_pending = False
        self._last_slider_update = 0
        
    def set_sprite_regions(self, sprites: List[Tuple[int, float]]):
        """Set sprite data and calculate regions lazily"""
        self._sprite_data = sprites
        self._sprite_regions = []  # Clear existing regions
        self._region_calculation_pending = True
        
        # Enable smart mode checkbox
        self.smart_mode_checkbox.setEnabled(True)
        
        # Auto-enable if significant number of sprites
        if len(sprites) > 10:
            self.smart_mode_checkbox.setChecked(True)
    
    def _calculate_regions_if_needed(self):
        """Lazy calculation of regions"""
        if self._region_calculation_pending and self._sprite_data:
            try:
                self._sprite_regions = self._region_detector.detect_regions(self._sprite_data)
                self._setup_region_mapping()
                self._region_calculation_pending = False
                
                # Update UI elements
                self._update_region_ui()
            except Exception as e:
                logger.exception("Error calculating sprite regions")
                self._sprite_regions = []
    
    def _on_offset_slider_changed(self, value: int):
        """Debounced slider change handler"""
        current_time = time.time()
        
        # Debounce rapid slider movements
        if current_time - self._last_slider_update < 0.016:  # 60 FPS
            if not self._slider_update_pending:
                self._slider_update_pending = True
                QTimer.singleShot(16, lambda: self._process_slider_change(value))
            return
        
        self._last_slider_update = current_time
        self._process_slider_change(value)
```

## 10. Import/Export Integration

### Enhanced Sprite List Export
```python
class RegionAwareExporter:
    """Exports sprite lists with region metadata"""
    
    def export_sprites_with_regions(self, sprites: List[Tuple[int, float]], 
                                   regions: List[SpriteRegion], 
                                   output_path: str):
        """Export sprite list with region information"""
        export_data = {
            "version": "2.0",
            "exported_at": time.time(),
            "sprites": [],
            "regions": [],
            "region_settings": {
                "gap_threshold": regions[0].detector.gap_threshold if regions else 0x10000,
                "min_sprites_per_region": 2,
                "merge_small_regions": True
            }
        }
        
        # Export sprite data
        for offset, quality in sprites:
            region_id = self._find_region_for_sprite(offset, regions)
            export_data["sprites"].append({
                "offset": offset,
                "quality": quality,
                "region_id": region_id
            })
        
        # Export region metadata
        for region in regions:
            export_data["regions"].append({
                "id": region.region_id,
                "start": region.start_offset,
                "end": region.end_offset,
                "type": region.region_type,
                "name": region.custom_name,
                "color": region.custom_color,
                "confidence": region.confidence_score,
                "sprite_count": region.sprite_count
            })
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)
    
    def import_sprites_with_regions(self, import_path: str) -> Tuple[List[Tuple[int, float]], List[SpriteRegion]]:
        """Import sprite list and reconstruct regions"""
        with open(import_path, 'r') as f:
            data = json.load(f)
        
        # Reconstruct sprites
        sprites = [(s["offset"], s["quality"]) for s in data["sprites"]]
        
        # Reconstruct regions if available
        if "regions" in data and data.get("version") == "2.0":
            regions = []
            for r in data["regions"]:
                region = SpriteRegion(
                    region_id=r["id"],
                    start_offset=r["start"],
                    end_offset=r["end"],
                    sprite_offsets=[],  # Will be populated
                    sprite_qualities=[],
                    average_quality=0,
                    sprite_count=r["sprite_count"],
                    size_bytes=r["end"] - r["start"],
                    density=0,
                    region_type=r.get("type", "unknown"),
                    custom_name=r.get("name"),
                    custom_color=r.get("color"),
                    confidence_score=r.get("confidence", 1.0)
                )
                regions.append(region)
            
            # Populate sprite lists for each region
            for sprite_data in data["sprites"]:
                region_id = sprite_data.get("region_id")
                if region_id is not None and region_id < len(regions):
                    regions[region_id].sprite_offsets.append(sprite_data["offset"])
                    regions[region_id].sprite_qualities.append(sprite_data["quality"])
            
            # Recalculate derived fields
            for region in regions:
                if region.sprite_qualities:
                    region.average_quality = statistics.mean(region.sprite_qualities)
                    region.density = len(region.sprite_offsets) / (region.size_bytes / 1024)
            
            return sprites, regions
        else:
            # Legacy format - auto-detect regions
            detector = SpriteRegionDetector()
            regions = detector.detect_regions(sprites)
            return sprites, regions
```

## 11. Accessibility Features

### Screen Reader Support
```python
class AccessibleRegionWidget(QWidget):
    """Region widget with full accessibility support"""
    
    def __init__(self):
        super().__init__()
        self._setup_accessibility()
    
    def _setup_accessibility(self):
        """Setup screen reader announcements"""
        # Enable accessibility
        self.setAccessibleName("Smart Offset Navigation")
        self.setAccessibleDescription("Navigate through sprite regions in ROM")
    
    def _announce_region_change(self, old_region: int, new_region: int):
        """Announce region changes to screen readers"""
        if new_region < len(self._sprite_regions):
            region = self._sprite_regions[new_region]
            announcement = (
                f"Entered {region.description}. "
                f"{region.sprite_count} sprites, "
                f"{region.quality_category} quality. "
                f"Press Tab for region statistics."
            )
            
            # Use Qt's accessibility framework
            QAccessible.updateAccessibility(
                QAccessibleEvent(
                    self,
                    QAccessible.Event.Alert
                )
            )
            
            # Also use platform-specific announcements
            if sys.platform == "win32":
                self._announce_windows(announcement)
            elif sys.platform == "darwin":
                self._announce_macos(announcement)
            else:
                self._announce_linux(announcement)
    
    def _announce_windows(self, text: str):
        """Windows screen reader announcement"""
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)
        except ImportError:
            logger.debug("Windows TTS not available")
    
    def keyPressEvent(self, event: QKeyEvent):
        """Enhanced keyboard navigation for accessibility"""
        if event.key() == Qt.Key.Key_Tab:
            # Read current region statistics
            self._read_current_region_stats()
        elif event.key() == Qt.Key.Key_Question:
            # Read keyboard shortcuts help
            self._read_keyboard_help()
        else:
            super().keyPressEvent(event)
```

### High Contrast Mode
```python
class HighContrastRegionPainter:
    """Region painter with high contrast mode support"""
    
    def __init__(self):
        self.high_contrast_enabled = self._detect_high_contrast()
    
    def _detect_high_contrast(self) -> bool:
        """Detect if system is in high contrast mode"""
        # Check system settings
        app = QApplication.instance()
        if app:
            palette = app.palette()
            # Simple heuristic for high contrast
            bg_color = palette.color(QPalette.ColorRole.Window)
            fg_color = palette.color(QPalette.ColorRole.WindowText)
            contrast_ratio = self._calculate_contrast_ratio(bg_color, fg_color)
            return contrast_ratio > 10.0
        return False
    
    def get_region_colors(self, region: SpriteRegion, is_current: bool) -> Tuple[QColor, QColor]:
        """Get appropriate colors for region based on contrast mode"""
        if self.high_contrast_enabled:
            if is_current:
                return QColor(Qt.GlobalColor.yellow), QColor(Qt.GlobalColor.black)
            else:
                return QColor(Qt.GlobalColor.white), QColor(Qt.GlobalColor.black)
        else:
            # Normal colors
            if is_current:
                return QColor(100, 150, 255, 60), QColor(100, 150, 255)
            else:
                return QColor(80, 80, 80, 40), QColor(120, 120, 120)
```

## 12. Region History and Navigation

### Navigation History Manager
```python
class RegionNavigationHistory:
    """Tracks region navigation history for back/forward functionality"""
    
    def __init__(self, max_history: int = 50):
        self.history: List[Tuple[int, int]] = []  # (region_index, offset)
        self.current_index: int = -1
        self.max_history = max_history
    
    def add_navigation(self, region_index: int, offset: int):
        """Add a navigation point to history"""
        # Remove any forward history if we're not at the end
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]
        
        # Add new entry
        self.history.append((region_index, offset))
        
        # Limit history size
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.current_index += 1
    
    def can_go_back(self) -> bool:
        """Check if back navigation is available"""
        return self.current_index > 0
    
    def can_go_forward(self) -> bool:
        """Check if forward navigation is available"""
        return self.current_index < len(self.history) - 1
    
    def go_back(self) -> Optional[Tuple[int, int]]:
        """Navigate back in history"""
        if self.can_go_back():
            self.current_index -= 1
            return self.history[self.current_index]
        return None
    
    def go_forward(self) -> Optional[Tuple[int, int]]:
        """Navigate forward in history"""
        if self.can_go_forward():
            self.current_index += 1
            return self.history[self.current_index]
        return None
```

## 13. Testing Strategy

### Unit Tests
```python
# tests/test_sprite_regions.py
def test_region_detection_basic():
    """Test basic region detection"""
    detector = SpriteRegionDetector(gap_threshold=0x1000)
    sprites = [
        (0x1000, 0.8),
        (0x1100, 0.9),
        (0x1200, 0.7),
        (0x5000, 0.8),  # Gap - new region
        (0x5100, 0.9),
    ]
    
    regions = detector.detect_regions(sprites)
    assert len(regions) == 2
    assert regions[0].sprite_count == 3
    assert regions[1].sprite_count == 2

def test_region_mapping():
    """Test slider to offset mapping"""
    widget = ManualOffsetWidget()
    # Test implementation...

def test_performance_large_sprite_count():
    """Test performance with many sprites"""
    sprites = [(i * 0x100, random.random()) for i in range(10000)]
    
    start = time.time()
    detector = SpriteRegionDetector()
    regions = detector.detect_regions(sprites)
    elapsed = time.time() - start
    
    assert elapsed < 0.1  # Should complete in under 100ms
    assert len(regions) > 0
```

### Integration Tests
```python
# tests/test_smart_mode_integration.py
def test_scan_to_smart_mode_flow(qtbot, main_window):
    """Test complete flow from scan to smart mode"""
    # 1. Load ROM
    # 2. Start scan
    # 3. Wait for completion
    # 4. Verify smart mode enabled
    # 5. Test navigation
```

## 14. Implementation Order

1. **Phase 1: Core Data Structures**
   - Create sprite_regions.py with SpriteRegion and SpriteRegionDetector
   - Add unit tests for region detection

2. **Phase 2: UI Foundation**
   - Add smart mode UI elements to ManualOffsetWidget
   - Implement dual-mode slider mapping
   - Add region navigation controls

3. **Phase 3: Integration**
   - Connect ScanControlsPanel completion to region detection
   - Update ROMMapWidget for region visualization
   - Wire up all signals and events

4. **Phase 4: Polish**
   - Add caching support
   - Implement settings persistence
   - Add error handling and edge cases
   - Performance optimization

5. **Phase 5: Testing**
   - Complete unit test suite
   - Integration tests
   - Performance testing
   - User acceptance testing

## 15. Future Enhancements

1. **Advanced Region Detection**
   - Machine learning-based region detection
   - User-adjustable region boundaries
   - Region naming and annotations

2. **Enhanced Visualization**
   - Heatmap overlay showing sprite density
   - Mini-map in slider track
   - Region preview on hover

3. **Smart Navigation**
   - Predictive loading of nearby regions
   - Bookmarking favorite regions
   - Region-based search

4. **Export/Import**
   - Export region definitions
   - Share region maps between users
   - Import custom region layouts

---

## Summary

This enhanced implementation plan provides a comprehensive approach to adding smart offset control to SpritePal. The feature will significantly improve navigation efficiency for users working with large ROMs by focusing only on areas containing sprite data. 

Key enhancements include:
- **Enhanced Data Structures**: Region confidence scoring, type classification, and usage tracking
- **Advanced UI Components**: Region overview minimap, statistics panel, visual slider markers, and smooth animations
- **Performance Optimizations**: Multi-threaded region detection, real-time updates, and lazy calculation
- **Accessibility Features**: Full screen reader support and high contrast mode
- **User Control**: Interactive region management with merge/split/rename capabilities
- **Integration Improvements**: Smart Find Next/Previous, dynamic region updates, and enhanced import/export
- **Navigation Features**: History tracking with back/forward support and keyboard shortcuts

The modular design ensures the feature integrates seamlessly with existing functionality while maintaining backward compatibility through the dual-mode interface. The implementation follows a phased approach allowing incremental development and testing.