# Visual Guide: Auto Monotonic Binning Button

## Button Layout

The binning controls now include three buttons in this order:

```
┌────────────────────────────────────────────────────────────────┐
│                     BINNING CONTROLS                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────┐  ┌──────────────────────────┐  │
│  │  Fine Binning on         │  │  ⚡ Auto Monotonic       │  │
│  │  Selected                │  │  Binning                 │  │
│  │  [Green Button]          │  │  [Purple Gradient]       │  │
│  └──────────────────────────┘  └──────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────┐                                │
│  │  Reset Binning           │                                │
│  │  [Red Button]            │                                │
│  └──────────────────────────┘                                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Button Styles

### 1. Fine Binning on Selected (Green)
- **Color**: Green (#2ea043)
- **State**: Enabled only when 2+ bins selected
- **Function**: Manual merge of selected bins
- **Icon**: None

### 2. ⚡ Auto Monotonic Binning (Purple Gradient)
- **Color**: Purple gradient (#667eea → #764ba2)
- **State**: Always enabled
- **Function**: Automatic merge for monotonicity
- **Icon**: ⚡ Lightning bolt (pulsing)
- **Effects**: 
  - Shimmer on hover
  - Glow shadow
  - Smooth transitions

### 3. Reset Binning (Red)
- **Color**: Red (#da3633)
- **State**: Always enabled
- **Function**: Reset to coarse binning
- **Icon**: None

## Interaction Flow

```
User Clicks "⚡ Auto Monotonic Binning"
        ↓
Notification: "Running auto-monotonic binning for [column]..."
        ↓
Backend processes (1-3 seconds)
        ↓
Table updates with merged bins
        ↓
WOE/IV charts refresh
        ↓
Notification: "Auto-binning completed: X merges performed, 
               Y → Z bins, WOE trend: increasing/decreasing, 
               monotonic: Yes/No"
```

## Visual Differences from Other Buttons

### Fine Binning Button
```css
.fine-bin-btn {
  background: solid green;
  hover: lighter green + glow;
}
```

### Auto Monotonic Button (NEW!)
```css
.auto-monotonic-btn {
  background: linear-gradient(purple shades);
  icon: ⚡ with pulse animation;
  hover: reverse gradient + shimmer effect;
  shadow: purple glow;
}
```

### Reset Button
```css
.reset-bin-btn {
  background: solid red;
  hover: lighter red;
}
```

## Button States

### Auto Monotonic Button States

| State | Appearance | Behavior |
|-------|------------|----------|
| **Normal** | Purple gradient, lightning icon | Ready to click |
| **Hover** | Reverse gradient, shimmer effect | Shows interactivity |
| **Active** | Slightly depressed | Processing click |
| **Processing** | (same as normal) | Backend running |
| **Success** | (same as normal) | Notification shows result |

## Notification Examples

### Success Cases

```
✓ Auto-binning completed for age: 3 merges performed, 
  10 → 7 bins, WOE trend: decreasing, monotonic: Yes
```

```
✓ Auto-binning completed for education: 2 merges performed, 
  5 → 3 bins, WOE trend: increasing, monotonic: Yes
```

```
✓ Auto-binning completed for income: 0 merges performed, 
  8 → 8 bins, WOE trend: decreasing, monotonic: Yes
  (Already monotonic!)
```

### Error Cases

```
✗ Error in auto-binning: Variable not found in dataset
```

```
✗ Error in auto-binning: Target variable missing
```

## Accessibility

- **Keyboard Navigation**: Tab key reaches button
- **Screen Readers**: 
  - Label: "Run auto-monotonic binning for [column]"
  - Description: "Automatically merge bins to achieve monotonic WOE trend"
- **Focus State**: Blue outline on focus
- **ARIA**: Proper labels and descriptions

## Responsive Design

The button maintains same dimensions as other buttons:
- **Width**: Auto (content-based)
- **Height**: 32px
- **Padding**: 0.35rem 1rem
- **Font Size**: 13px
- **Font Weight**: 600

## Color Accessibility

The purple gradient (#667eea → #764ba2) provides:
- ✓ Sufficient contrast with white text (WCAG AA compliant)
- ✓ Distinct from green (fine binning) and red (reset)
- ✓ Futuristic appearance matching "auto" functionality

## Animation Details

### 1. Lightning Icon Pulse
```css
@keyframes pulse {
  0%, 100%: opacity 1, scale 1
  50%: opacity 0.8, scale 1.1
}
Duration: 2s infinite
```

### 2. Shimmer Effect
```css
Shimmer moves left to right on hover
Duration: 0.5s
Effect: White transparent gradient
```

### 3. Button Hover
```css
Transform: translateY(-2px)
Shadow: Enhanced purple glow
Background: Reversed gradient
```

## Usage Tips

1. **When to Use**:
   - Want monotonic WOE automatically
   - Don't want to manually select bins
   - Need quick optimization

2. **When NOT to Use**:
   - Need specific business logic merges
   - Want granular control
   - Already have optimal binning

3. **After Using**:
   - Review the merges
   - Check if they make business sense
   - Can still manually adjust with Fine Binning
   - Can Unmerge specific bins if needed

## Developer Notes

### CSS Classes
- `.auto-monotonic-btn`: Main button class
- `.btn-icon`: Lightning icon styling
- Inherits hover/focus from base button classes

### JavaScript Functions
- `runAutoMonotonicBinning(col: string)`: Main handler
- Calls `/api/auto-monotonic-binning` endpoint
- Updates multiple state variables
- Triggers metric recalculation

### Dependencies
- Backend: `auto_monotonic_binning.py`
- API: `/api/auto-monotonic-binning`
- Frontend: React state management
- Styling: CSS animations and gradients
