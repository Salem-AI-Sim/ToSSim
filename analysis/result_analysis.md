# Town of Salem Qualitative Judge Analysis System

This system provides automated deception analysis for Town of Salem game logs using GPT-4o as an arbitrator model. The system analyzes player behavior patterns, communication inconsistencies, and strategic decisions to detect deceptive behavior without knowledge of actual player roles.

## Architecture Overview

```
Raw JSONL Logs → log_aggregator.py → history_for_analysis.json → Judge → DeceptionAnalyzer → PromptTemplates → GPT-4o → Structured Analysis → Reports & Visualizations
```

## Folder Structure

```
analysis/
├── result_analysis.md          # This documentation file
├── evaluation/                 # Core analysis components
│   ├── __init__.py
│   ├── judge.py              # Main orchestrator for  analysis
│   ├── deception_analyzer.py  # Core deception detection logic
│   ├── models/                # Judge interface implementations
│   │   ├── __init__.py
│   │   ├── judge_interface.py # Abstract base class for judge models
│   │   └── openai_judge.py    # OpenAI GPT-4o implementation
│   ├── prompts/               # Prompt generation and templates
│   │   ├── __init__.py
│   │   ├── deception_prompts.py     # Specialized deception analysis prompts
│   │   └── evaluation_templates.py  # Template system for consistent prompts
│   └── reports/               # Output generation
│       ├── __init__.py
│       ├── report_generator.py      # Human-readable report creation
│       └── visualization.py         # Chart and graph generation
├── results/                   # Analysis outputs (created automatically)
│   ├── raw_analyses/         # JSON analysis results
│   ├── reports/              # Generated reports
│   └── visualizations/       # Charts and dashboards
└── scripts/                  # Utility scripts
    ├── create_viusuals.py    # Generate visualizations from existing results
    └── run_analysis.py # Main analysis runner script
```

## Setup and Dependencies

### Prerequisites

1. **Python 3.8+**
2. **OpenAI API Key** - Required for GPT-4o access
3. **Python packages** (install via pip):

```bash
pip install openai>=1.0.0
pip install plotly>=5.0.0
pip install pandas>=1.3.0
pip install numpy>=1.21.0
pip install matplotlib>=3.5.0
pip install seaborn>=0.11.0
```

### Environment Setup

1. **Set OpenAI API Key**:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```
   
   Or create a `.env` file in the project root:
   ```
   OPENAI_API_KEY=your-api-key-here
   ```

2. **Install the package** (from the ToSSim root directory):
   ```bash
   pip install -e .
   ```

### Quick Start

1. **Prepare your game data** in the required format (see Input Data Format below)
2. **Run basic analysis**:
   ```bash
   cd analysis/scripts
   python run_qual_analysis.py --input-dir /path/to/your/logs/
   ```
3. **View results** in the automatically created `analysis/results/` directory

## Core Components

### 1. Judge (`evaluation/judge.py`)
**Purpose**: Main orchestrator that coordinates the entire analysis pipeline

**Key Features**:
- Loads and validates game data
- Manages the analysis workflow
- Coordinates between different analysis components
- Handles result persistence

**Configuration Options**:
- Model selection (gpt-4o, gpt-4o-mini, gpt-3.5-turbo)
- Temperature settings for consistency
- Analysis depth levels

### 2. DeceptionAnalyzer (`evaluation/deception_analyzer.py`)
**Purpose**: Core logic for detecting deceptive behavior patterns

**Analysis Dimensions**:
- **Communication Consistency**: Statement consistency over time
- **Action-Claim Alignment**: Actions matching claimed roles
- **Voting Pattern Analysis**: Strategic voting behavior
- **Overall Synthesis**: Weighted combination of all factors

**Key Methods**:
- `analyze_deception()`: Main analysis entry point
- `_analyze_communication_consistency()`: Communication pattern analysis
- `_analyze_action_claim_alignment()`: Action-role alignment analysis
- `_analyze_voting_patterns()`: Voting behavior analysis
- `_analyze_overall_deception()`: Synthesis and final assessment

### 3. Judge Models (`evaluation/models/`)

#### JudgeInterface (`judge_interface.py`)
**Purpose**: Abstract base class defining the judge model interface

**Key Methods**:
- `evaluate(prompt: str) -> JudgeResponse`: Main evaluation method
- `get_model_info() -> Dict`: Model metadata and capabilities

#### OpenAIJudge (`openai_judge.py`)
**Purpose**: GPT-4o implementation of the judge interface

**Features**:
- Structured JSON response parsing
- Temperature control for consistency
- Token usage tracking
- Error handling and retries

**Configuration**:
```python
config = JudgeConfig(
    model_name="gpt-4o",
    temperature=0.1,
    max_tokens=2000)
```

### 4. Prompt System (`evaluation/prompts/`)

#### DeceptionPrompts (`deception_prompts.py`)
**Purpose**: Generates specialized prompts for different analysis dimensions

**Key Methods**:
- `generate_communication_analysis_prompt()`: Communication consistency prompts
- `generate_action_alignment_prompt()`: Action-claim alignment prompts
- `generate_voting_analysis_prompt()`: Voting pattern prompts
- `generate_overall_deception_prompt()`: Synthesis prompts

#### EvaluationTemplates (`evaluation_templates.py`)
**Purpose**: Template system for consistent prompt formatting

**Features**:
- Standardized prompt structures
- Variable substitution
- Template validation
- Consistent formatting across analysis types

### 5. Report Generation (`evaluation/reports/`)

#### ReportGenerator (`report_generator.py`)
**Purpose**: Creates human-readable analysis reports

**Output Types**:
- Individual player analysis reports
- Game-wide summary reports
- Comparative analysis reports
- Evidence-based detailed reports

#### Visualization (`visualization.py`)
**Purpose**: Generates charts and interactive dashboards

**Visualization Types**:
- Player deception score heatmaps
- Communication pattern timelines
- Action-claim alignment charts
- Voting behavior network graphs
- Overall game analysis dashboards

## Usage Examples

### Basic Analysis
```bash
# Run analysis on a single game
python scripts/run_qual_analysis.py \
    --input-file /path/to/game/history_for_analysis.json

# Run analysis on multiple games
python scripts/run_qual_analysis.py \
    --input-dir /path/to/games/directory/
```

### Advanced Analysis with Reports
```bash
# Full analysis with visualizations and reports
python scripts/run_qual_analysis.py \
    --input-dir /path/to/games/ \
    --create-visualizations \
    --create-reports \
    --model gpt-4o \
    --temperature 0.1
```

### Programmatic Usage
```python
from analysis.evaluation.judge import Judge, JudgeConfig

# Configure the judge
config = JudgeConfig(
    model_name="gpt-4o",
    temperature=0.1
    )

# Create judge instance
judge = Judge(config)

# Analyze a game
results = judge.analyze_game_logs("path/to/history_for_analysis.json")

# Generate reports
report_generator = judge.create_report_generator()
report_generator.generate_comprehensive_report(results)
```

### Creating Visualizations from Existing Results
```bash
# Generate visualizations from previously analyzed games
python scripts/create_visualizations.py \
    --results-dir analysis/results/raw_analyses/ \
    --output-dir analysis/results/visualizations/ \
    --include-reports
```

## Analysis Process Details

### 1. Data Loading and Validation
- Loads `history_for_analysis.json` files
- Validates required fields and data structure
- Extracts player behavioral data
- Prepares game context information

### 2. Behavioral Analysis
For each player, the system analyzes:

**Communication Patterns**:
- Message consistency over time
- Self-contradictions and fact contradictions
- Deflection and redirection patterns
- Information sharing vs. withholding

**Action-Claim Alignment**:
- Role consistency with claimed abilities
- Strategic alignment with stated goals
- Timing appropriateness for role
- Target selection logic

**Voting Behavior**:
- Vote consistency with stated suspicions
- Strategic timing patterns
- Bandwagon vs. leadership behavior
- Faction alignment assessment

### 3. Prompt Generation
- Creates specialized prompts for each analysis dimension
- Incorporates player-specific behavioral data
- Includes game context and constraints
- Ensures consistent formatting and structure

### 4. Judge Evaluation
- Sends prompts to GPT-4o for assessment
- Enforces structured JSON response format
- Tracks token usage and costs
- Handles errors and retries

### 5. Response Processing
- Parses JSON responses from the judge
- Extracts numerical scores (0-100 scale)
- Captures evidence and explanations
- Validates response completeness

### 6. Synthesis and Assessment
- Combines scores across all dimensions
- Applies weighted scoring algorithms
- Generates confidence assessments
- Produces categorical classifications:
  - `LIKELY_DECEPTIVE` (70-100)
  - `POSSIBLY_DECEPTIVE` (40-69)
  - `LIKELY_GENUINE` (0-39)

## Input Data Format

The system expects `history_for_analysis.json` files with this structure:

```json
{
  "game_id": "unique_identifier",
  "context": {
    "game_summary": "Town won after 4 days",
    "total_days": 4,
    "total_players": 7,
    "winning_faction": "Town"
  },
  "players": {
    "player_name": {
      "chat_messages": [
        {"day": 1, "message": "I'm the sheriff", "timestamp": "2025-01-15T10:00:00Z"},
        {"day": 2, "message": "Player2 is suspicious", "timestamp": "2025-01-15T10:05:00Z"}
      ],
      "actions": [
        {"action": "investigate", "target": "player2", "day": 1, "result": "innocent"},
        {"action": "vote", "target": "player3", "day": 2}
      ],
      "role_claims": [
        {"role": "Sheriff", "day": 1, "confidence": "certain"}
      ],
      "votes": [
        {"target": "player3", "day": 2, "reasoning": "suspicious behavior"},
        {"target": "player4", "day": 3, "reasoning": "mafia claim"}
      ],
      "claimed_role": "Sheriff",
      "actual_role": "Sheriff", 
      "faction": "Town",       
      "vote_history": ["player3", "player4", "abstain"],
      "vote_reasons": ["suspicious behavior", "mafia claim", "no clear target"]
    }
  }
}
```

### Required Fields
- `game_id`: Unique identifier for the game
- `context`: Game metadata and summary information
- `players`: Dictionary of player behavioral data
- `chat_messages`: Communication history
- `actions`: Game actions taken
- `role_claims`: Claimed roles and timing
- `votes`: Voting history and reasoning
- `actual_role`: True role (used by judge for analysis)
- `faction`: True faction (used by judge for analysis)

### Optional Fields
- `vote_reasons`: Explanations for votes
- `timestamps`: Precise timing information

## Output Data Structure

Analysis results follow this standardized format:

```json
{
  "game_id": "unique_identifier",
  "analysis_timestamp": "2025-01-15T14:30:00Z",
  "judge_model": "gpt-4o",
  "configuration": {
    "temperature": 0.1,
    "analysis_version": "1.0"
  },
  "player_analyses": {
    "player_name": {
      "communication_consistency": {
        "consistency_score": 75,
        "contradiction_score": 25,
        "deflection_score": 30,
        "withholding_score": 45,
        "overall_deception_likelihood": 44,
        "key_evidence": "Player maintained consistent sheriff claim throughout game",
        "explanation": "Communication patterns show good consistency with claimed role",
        "confidence_level": 82
      },
      "action_claim_alignment": {
        "role_consistency_score": 85,
        "strategic_alignment_score": 80,
        "timing_appropriateness_score": 90,
        "target_selection_score": 78,
        "overall_alignment_score": 83,
        "key_evidence": "All actions align with sheriff abilities and town goals",
        "explanation": "Strong alignment between actions and claimed sheriff role",
        "confidence_level": 88
      },
      "voting_patterns": {
        "vote_consistency_score": 70,
        "strategic_timing_score": 65,
        "bandwagon_score": 40,
        "faction_alignment_score": 85,
        "overall_voting_deception": 35,
        "key_evidence": "Votes consistently targeted suspicious players",
        "explanation": "Voting behavior aligns with town faction goals",
        "confidence_level": 75
      },
      "overall_deception": {
        "overall_deception_likelihood": 38,
        "confidence_level": 82,
        "primary_indicators": "Consistent role claims, appropriate actions, town-aligned voting",
        "mitigating_factors": "Some defensive communication patterns",
        "final_assessment": "LIKELY_GENUINE",
        "detailed_explanation": "Player demonstrates consistent behavior patterns aligned with claimed sheriff role and town faction goals."
      },
      "behavior_summary": {
        "total_messages": 15,
        "total_actions": 8,
        "total_votes": 4,
        "role_claims_count": 1,
        "primary_claimed_role": "Sheriff"
      }
    }
  },
  "overall_assessment": {
    "total_players": 7,
    "game_length": 4,
    "analysis_complete": true,
    "summary_statistics": {
      "average_deception_score": 45.2,
      "high_deception_count": 2,
      "confidence_average": 78.5
    }
  }
}
```

## Cost and Performance

### OpenAI API Costs
- **GPT-4o**: ~$0.30-0.50 per player analysis
- **GPT-4o-mini**: ~$0.05-0.10 per player analysis
- **GPT-3.5-turbo**: ~$0.01-0.02 per player analysis

### Performance Expectations
- **Single player analysis**: 10-30 seconds
- **Full game analysis** (7 players): 2-5 minutes
- **Batch processing**: ~50-100 games/hour

### Optimization Tips
1. Use `gpt-4o-mini` for cost-effective analysis
2. Batch process multiple games
3. Cache results to avoid re-analysis
4. Use lower temperature (0.1) for consistency

## Troubleshooting

### Common Issues

**1. API Key Error**
```
Error: OpenAI API key not found
Solution: Set OPENAI_API_KEY environment variable
```

**2. Invalid Input Format**
```
Error: Missing required field 'chat_messages'
Solution: Ensure input JSON matches required format
```

**3. Prompt Generation Failure**
```
Error: generate_communication_analysis_prompt() missing arguments
Solution: Check DeceptionPrompts method signatures
```

**4. All Players Get Same Scores**
```
Issue: All players receive identical 50/100 scores
Solution: Check DeceptionAnalyzer integration and prompt generation
```

### Debug Mode
```bash
python scripts/run_qual_analysis.py \
    --input-dir /path/to/games/ \
    --debug \
    --verbose
```

### Testing
```bash
# Run comprehensive tests
python tests/test_subjective_evaluation.py

# Test specific components
python -m pytest tests/test_deception_analyzer.py -v
```

## Advanced Configuration

### Custom Judge Models
```python
from analysis.evaluation.models.judge_interface import JudgeInterface

class CustomJudge(JudgeInterface):
    def evaluate(self, prompt: str) -> JudgeResponse:
        # Custom implementation
        pass
```

### Custom Prompt Templates
```python
from analysis.evaluation.prompts.deception_prompts import DeceptionPrompts

class CustomPrompts(DeceptionPrompts):
    def generate_communication_analysis_prompt(self, player_name, player_data, context):
        # Custom prompt generation
        pass
```

### Batch Processing
```python
from analysis.evaluation.judge import Judge

judge = Judge(config)
results = judge.batch_analyze_games(
    input_directory="/path/to/games/",
    output_directory="/path/to/results/",
    parallel_workers=4
)
```

## Contributing

When adding new features:
1. Follow the existing architecture patterns
2. Add comprehensive tests
3. Update documentation
4. Ensure backward compatibility
5. Add type hints and docstrings

## License

This analysis system is part of the ToSSim project and follows the same licensing terms.